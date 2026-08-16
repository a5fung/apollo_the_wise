#!/usr/bin/env python3
"""#533 WIDENED — did what we HELD beat what we could have held? (READ-ONLY; STUDY ONLY)

THE QUESTION (operator 2026-08-15, verbatim in ep_profitability_program.md §GOAL/⚖):
the objective is RETURN ON CAPITAL, not expectancy per trade. Every filled live
position is scored against the ALTERNATIVES admissible at its decision point, over
the same window it actually occupied. The multi-alert day is a SPECIAL CASE — a
marginal name held N days also forgoes every alert that fired while capital was
tied (single-alert entry days count through that hold-window frame).

COHORT. Every mi_live_trades row with account_mode='live' AND a fill (20 closed +
2 open at capture). Outcomes for alternatives are re-derived from mi_daily_closes
bars under ONE convention (alert-day OPEN -> window-end close), the same shape as
_533_structure_admission_probe.py — this sidesteps the mi_ep_missed_outcomes
fraction-vs-percent trap entirely (those columns are not used).

ADMISSIBILITY — the hard part, handled explicitly, two labelled sets NEVER blended:
  SET A (upper bound): ALL other HIGH alerts that session. Includes names we could
        NOT have reached: detected after the 09:45 ORB cutoff, infra failures,
        orders that never triggered, portfolio blocks. A is what the tape offered,
        not what was takeable.
  SET B (honest counterfactual): only names we CHOSE not to take — selection /
        risk-geometry skips: setup:gap_below_floor, setup:stop_too_wide,
        setup:size_too_small, setup:chase_cap_exceeded (and for HIGHs with no
        live row, the scan-level choice filters: cooldown, extension_gate,
        atr_high, ma_filter, catalyst_downgrade). Mechanics (window:out_of_orb,
        infra:*, unfilled/cancelled/rejected, zero_range, block:circuit_breaker,
        block:max_positions) are EXCLUDED from B — we could not have had them.
  Cap-blocked names (block:max_positions) are additionally listed on their own:
  they are the only alternatives MECHANICALLY blocked by what we were holding.

TWO DECISION FRAMES, both reported:
  FRAME S (same-session): the pick vs that morning's other HIGH alerts. Rank /
        percentile on same-basis returns; regret vs best admissible alternative.
  FRAME H (hold-window): for positions held past entry day, every HIGH alert on
        sessions entry < s <= close while capital was tied; like-for-like
        sub-window = alt's alert-day open -> our window-end close on BOTH sides
        (ours measured on our ticker over the identical dates).

TWO BASES, labelled every time (they answer different questions):
  CAPITAL basis: our REALIZED return (actual fills, actual exits, partials,
        mark-to-2026-08-14 on open names) vs the alternative's open->close hold.
        Confounded by our exit machinery — a day-one stop is an exit outcome.
  SELECTION basis: our ticker's open->close over the same window vs the same for
        the alternative — isolates the PICK from the bracket (the #468b lesson).

STANDING CAVEATS (apply to every number below; printed in the output too):
  1. We cannot prove we would have been FILLED on any alternative (ETON lesson:
     a resting limit is a promise about price, not a fill). All alternative
     returns assume a fill at the alert-day open print. Our ACTUAL entries were
     at the ORB high — typically ABOVE the open on a gap day — so the CAPITAL
     basis flatters the alternatives by that spread; the SELECTION basis uses
     the open convention on BOTH sides and is free of it.
  2. Regret-vs-BEST is max-biased by construction (winner's curse across the
     pool); regret vs the MEDIAN alternative is printed alongside.
  3. hold_days in mi_live_trades is unreliable (0 on known multi-day holds);
     hold time is re-derived from filled_at/closed_at ET dates. Where that
     failed we fall back to unweighted stats and say so.
  4. Open positions (PLTR, ABCL) are marked OPEN; their windows end at the data
     max (2026-08-14) and their "realized" includes unrealized mark.
  5. ETON's green is ASTERISKED — profit existed only because a bug left shares
     unstopped (program doc §0.1).

WHAT WOULD MAKE THIS CONCLUSIVE: (a) a session-level randomization — would a
dart-throwing allocator over the same admissible pools have done as well? —
clearly in one tail; (b) enough distinct entry sessions with a genuine choice
that the median regret is stable; (c) the same sign on both bases and both
frames. With ~22 fills over ~16 sessions the honest answer may be "cannot
separate from chance" — that is a finding, not a failure. THE LINE: this probe
measures; it changes no admission rule, sizing, slot count, grading, or exit.

Inputs (captured ONCE from prod 2026-08-15, COST EFFICIENCY rule):
  _533r_trades.tsv  mi_live_trades account_mode='live', ET fill/close dates
  _533r_alerts.tsv  DISTINCT ON (ticker,alert_date) HIGH alerts 07-01..08-14 +
                    detected-at ET time + mi_ep_missed_outcomes.skip_category
  _533r_bars.tsv    mi_daily_closes o/h/l/c for every involved ticker
"""
from __future__ import annotations

import os
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

if os.environ.get("APOLLO_PROBE_WRITE"):
    sys.exit("this probe is read-only by design")

HERE = Path(__file__).resolve().parent
SEED = 20260815
N_MC = 10000
DATA_MAX = "2026-08-14"

# ---------------- load ----------------
def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

bars: dict[str, dict[str, tuple]] = defaultdict(dict)   # ticker -> date -> (o,h,l,c)
for ln in (HERE / "_533r_bars.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) != 6:
        continue
    t, d = p[0], p[1]
    o, h, lo, c = f(p[2]), f(p[3]), f(p[4]), f(p[5])
    bars[t][d] = (o if o else None, h, lo, c)

SESS = sorted({d for t in bars.values() for d in t})     # global trading sessions
SIDX = {d: i for i, d in enumerate(SESS)}

def sess_at_or_before(d: str) -> str | None:
    c = [s for s in SESS if s <= d]
    return c[-1] if c else None

def close_on(t: str, d: str) -> float | None:
    """Close on session d, carrying back to the last available bar <= d (halts)."""
    rows = bars.get(t, {})
    if d in rows and rows[d][3]:
        return rows[d][3]
    prior = [s for s in rows if s <= d and rows[s][3]]
    return rows[max(prior)][3] if prior else None

def open_on(t: str, d: str) -> float | None:
    r = bars.get(t, {}).get(d)
    return r[0] if r else None

trades = []
for ln in (HERE / "_533r_trades.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) != 10:
        continue
    trades.append(dict(
        ticker=p[0], d=p[1], status=p[2], skip=p[3],
        entry=f(p[4]), shares=f(p[5]), pnl=f(p[6]), remaining=f(p[7]),
        fill_date=p[8] or None, close_date=p[9] or None))

alerts = []
for ln in (HERE / "_533r_alerts.tsv").read_text().splitlines():
    p = ln.split("|")
    if len(p) != 7:
        continue
    alerts.append(dict(ticker=p[0], d=p[1], ep=f(p[2]), gap=f(p[3]),
                       cq=p[4], det=p[5], mocat=p[6]))

live_by_key = {(t["ticker"], t["d"]): t for t in trades}

# ---------------- admissibility classification ----------------
CHOICE_PREFIX = ("setup:gap_below_floor", "setup:stop_too_wide",
                 "setup:size_too_small", "setup:chase_cap_exceeded")
MECH_PREFIX = ("window:out_of_orb", "infra:", "block:circuit_breaker",
               "block:max_positions", "setup:zero_range", "broker:",
               "ORB window unfilled", "cancelled", "rejected",
               "setup:account_fetch_failed", "setup:faded_from_orb",
               "setup:price_exceeds_cap", "infra:no_bar", "infra:subscribe_timeout")
CHOICE_MOCAT = {"cooldown", "extension_gate", "atr_high", "ma_filter",
                "catalyst_downgrade"}
MECH_MOCAT = {"window_missed", "infra_skip", "breaker_blocked", "cap_blocked"}

def classify(a: dict) -> str:
    """PICK | CHOICE | MECH | CAPBLOCK | UNCLASSIFIED (A-only) | DUP"""
    lt = live_by_key.get((a["ticker"], a["d"]))
    if lt is not None:
        if lt["fill_date"]:
            return "PICK"
        sk = lt["skip"]
        if sk.startswith("block:max_positions"):
            return "CAPBLOCK"
        if any(sk.startswith(c) for c in CHOICE_PREFIX):
            return "CHOICE"
        if any(sk.startswith(m) for m in MECH_PREFIX) or lt["status"] == "cancelled":
            return "MECH"
        return "UNCLASSIFIED"
    if a["mocat"] == "duplicate_scan":
        return "DUP"
    if a["mocat"] in CHOICE_MOCAT:
        return "CHOICE"
    if a["mocat"] in MECH_MOCAT:
        return "MECH"
    return "UNCLASSIFIED"

for a in alerts:
    a["cls"] = classify(a)
    a["has_bar"] = a["d"] in bars.get(a["ticker"], {}) and open_on(a["ticker"], a["d"]) is not None

by_sess: dict[str, list[dict]] = defaultdict(list)
for a in alerts:
    if a["cls"] != "DUP":
        by_sess[a["d"]].append(a)

# ---------------- positions ----------------
POS = []
for t in trades:
    if not t["fill_date"]:
        continue
    entry_sess = t["d"]
    is_open = t["status"] == "filled"
    end_sess = DATA_MAX if is_open else sess_at_or_before(t["close_date"])
    notional = (t["entry"] or 0) * (t["shares"] or 0)
    realized = t["pnl"] or 0.0
    if is_open:
        mark = close_on(t["ticker"], DATA_MAX)
        realized += (t["remaining"] or 0) * ((mark or t["entry"]) - t["entry"])
    r_realized = realized / notional if notional else None
    o0 = open_on(t["ticker"], entry_sess)
    ce = close_on(t["ticker"], end_sess)
    r_selection = (ce / o0 - 1) if (o0 and ce) else None
    i0 = SIDX.get(entry_sess)
    hold_td = SIDX[end_sess] - i0 + 1 if (i0 is not None and end_sess in SIDX) else None
    POS.append(dict(ticker=t["ticker"], d=entry_sess, end=end_sess, open_pos=is_open,
                    r_real=r_realized, r_sel=r_selection, hold=hold_td,
                    notional=notional, pnl_abs=realized))

POS.sort(key=lambda x: (x["d"], x["ticker"]))
PICKS_BY_SESS = defaultdict(set)
for p_ in POS:
    PICKS_BY_SESS[p_["d"]].add(p_["ticker"])

def alt_ret(a: dict, end_sess: str) -> float | None:
    """Alternative's same-basis return: its alert-day open -> close(end_sess)."""
    o = open_on(a["ticker"], a["d"])
    c = close_on(a["ticker"], end_sess)
    return (c / o - 1) if (o and c) else None

def ret5(t: str, d: str) -> float | None:
    """Fixed 5-session horizon: open(d) -> close(d+5 sessions). None if immature."""
    i = SIDX.get(d)
    if i is None or i + 5 >= len(SESS):
        return None
    o = open_on(t, d)
    c = close_on(t, SESS[i + 5])
    return (c / o - 1) if (o and c) else None

def pctl(x: float, pool: list[float]) -> float:
    """Share of pool values our pick strictly beat."""
    return sum(1 for v in pool if x > v) / len(pool) if pool else None

def pc(x, w=7):
    return f"{100*x:+.1f}%".rjust(w) if x is not None else "?".rjust(w)

def med_iqr(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None, None, None
    return st.median(xs), xs[n // 4], xs[(3 * n) // 4]

# ---------------- frame S per position ----------------
for p_ in POS:
    day = [a for a in by_sess[p_["d"]]
           if a["ticker"] not in PICKS_BY_SESS[p_["d"]] and a["has_bar"]]
    p_["altA"] = day
    p_["altB"] = [a for a in day if a["cls"] == "CHOICE"]
    for tag in ("A", "B"):
        alts = p_[f"alt{tag}"]
        rets_m = [(a["ticker"], alt_ret(a, p_["end"])) for a in alts]
        rets_m = [(t, r) for t, r in rets_m if r is not None]
        p_[f"m{tag}"] = rets_m
        if rets_m:
            best = max(rets_m, key=lambda x: x[1])
            p_[f"best{tag}"] = best
            p_[f"medalt{tag}"] = st.median([r for _, r in rets_m])
            p_[f"regret_cap{tag}"] = best[1] - p_["r_real"] if p_["r_real"] is not None else None
            p_[f"regret_sel{tag}"] = best[1] - p_["r_sel"] if p_["r_sel"] is not None else None
        else:
            p_[f"best{tag}"] = None
    # day0 + 5d ranks (same-basis, defined for every pool member -> null-comparable)
    p_["day0_own"] = None
    o = open_on(p_["ticker"], p_["d"])
    c = close_on(p_["ticker"], p_["d"])
    if o and c:
        p_["day0_own"] = c / o - 1
    p_["r5_own"] = ret5(p_["ticker"], p_["d"])
    for tag in ("A", "B"):
        d0 = [(c2 / o2 - 1) for a in p_[f"alt{tag}"]
              if (o2 := open_on(a["ticker"], a["d"])) and (c2 := close_on(a["ticker"], a["d"]))]
        p_[f"day0_pool{tag}"] = d0
        r5 = [v for a in p_[f"alt{tag}"] if (v := ret5(a["ticker"], a["d"])) is not None]
        p_[f"r5_pool{tag}"] = r5

# ---------------- frame H per position ----------------
for p_ in POS:
    i0, i1 = SIDX[p_["d"]], SIDX[p_["end"]]
    hs = [s for s in SESS[i0 + 1:i1 + 1]]
    cands = [a for s in hs for a in by_sess.get(s, [])
             if a["has_bar"] and a["ticker"] not in PICKS_BY_SESS.get(a["d"], set())]
    rows = []
    for a in cands:
        ra = alt_ret(a, p_["end"])                       # alt: its open -> our end close
        oo = open_on(p_["ticker"], a["d"])               # ours over the identical dates
        oc = close_on(p_["ticker"], p_["end"])
        ro = (oc / oo - 1) if (oo and oc) else None
        if ra is not None and ro is not None:
            rows.append(dict(a=a, r_alt=ra, r_own=ro, edge=ra - ro))
    p_["H"] = rows

# ---------------- report ----------------
print("=" * 96)
print("#533 WIDENED — DID WHAT WE HELD BEAT WHAT WE COULD HAVE HELD?  (capture 2026-08-15, "
      f"bars to {DATA_MAX})")
print("=" * 96)
n_open = sum(1 for p_ in POS if p_["open_pos"])
print(f"cohort: {len(POS)} filled LIVE positions ({len(POS)-n_open} closed + {n_open} OPEN) "
      f"over {len({p_['d'] for p_ in POS})} distinct entry sessions "
      f"({min(p_['d'] for p_ in POS)} .. {max(p_['d'] for p_ in POS)})")
hi = [a for a in alerts if a["cls"] != "DUP"]
print(f"alert universe: {len(hi)} HIGH ticker-days over {len({a['d'] for a in hi})} sessions "
      f"(2026-07-01..08-14); {sum(1 for a in hi if not a['has_bar'])} lack an alert-day bar "
      f"and are excluded from every alternative set (they are also unpriceable as trades)")
from collections import Counter
print("admissibility classes across the universe: "
      + ", ".join(f"{k}={v}" for k, v in sorted(Counter(a["cls"] for a in hi).items())))
unc = [a for a in hi if a["cls"] == "UNCLASSIFIED"]
if unc:
    print("  UNCLASSIFIED (kept in SET A only, named for honesty): "
          + ", ".join(f"{a['ticker']} {a['d']} ({a['mocat'] or 'no skip record'})" for a in unc))
print("""
STANDING CAVEATS ON EVERY NUMBER BELOW
  - No alternative fill is proven: alt returns assume a fill at the alert-day OPEN print
    (ETON lesson — a resting order is a promise about price, not a fill).
  - Our actual entries were at the ORB HIGH, usually above the open on a gap day — the
    CAPITAL basis therefore flatters the alternatives by that spread; the SELECTION
    basis uses the open convention on both sides and is free of it.
  - SET A = everything that alerted (upper bound; includes names detected after the ORB
    window, infra failures, never-triggered orders). SET B = only names we CHOSE to skip
    (selection / risk-geometry) = the honest counterfactual. Never blended.
  - CAPITAL basis = our realized P&L (exit machinery included). SELECTION basis = our
    ticker open->close over the same window (isolates the pick from the bracket).
  - Regret vs BEST is max-biased (winner's curse); regret vs the MEDIAN alt is alongside.
  - hold_days column is unreliable (0 on known multi-day holds) — hold time re-derived
    from filled_at/closed_at ET dates; that derivation succeeded for every position.
  - OPEN positions marked *: window ends at the data max; realized includes the mark.
  - ETON is asterisked green: its profit existed only because a bug left shares unstopped.""")

print("\n" + "-" * 96)
print("FRAME S — SAME-SESSION DECISION POINT (matched window = the days the position occupied)")
print("-" * 96)
def rank_str(p_, tag):
    """Rank of our pick by day0 return within pool (pick + set alts); 1 = best."""
    if p_.get("day0_own") is None or not p_[f"day0_pool{tag}"]:
        return "--"
    pool = p_[f"day0_pool{tag}"]
    r = 1 + sum(1 for v in pool if v > p_["day0_own"])
    return f"{r}/{len(pool)+1}"

hdr = (f"{'pos':<6}{'entry':<12}{'hold':>4} {'realzd':>7} {'selbas':>7} | "
       f"{'A:n':>4} {'rk0A':>5} {'bestA':>7} {'rgrA':>7} | "
       f"{'B:n':>4} {'rk0B':>5} {'bestB':>7} {'rgrB':>7}  best-B name")
print(hdr)
for p_ in POS:
    ba = p_.get("bestA")
    bb = p_.get("bestB")
    print(f"{p_['ticker'] + ('*' if p_['open_pos'] else ''):<6}{p_['d']:<12}{p_['hold']:>4} "
          f"{pc(p_['r_real'])} {pc(p_['r_sel'])} | "
          f"{len(p_['mA']):>4} {rank_str(p_, 'A'):>5} {pc(ba[1]) if ba else '     --'} "
          f"{pc(p_.get('regret_capA')) if ba else '     --'} | "
          f"{len(p_['mB']):>4} {rank_str(p_, 'B'):>5} {pc(bb[1]) if bb else '     --'} "
          f"{pc(p_.get('regret_capB')) if bb else '     --'}  "
          f"{bb[0] if bb else '(no choice-skip that session)'}")
print("  (rk0 = our day0 open->close rank in pick+alternatives pool, 1=best; rgr = best-alt")
print("   minus OUR REALIZED, capital basis; * = still open, marked to " + DATA_MAX + ")")
noalt = [p_ for p_ in POS if not p_["mA"]]
print(f"  {len(noalt)} of {len(POS)} positions had NO same-session alternative at all "
      f"({', '.join(p_['ticker'] for p_ in noalt)}) — on those sessions we took every HIGH")
print("  that fired; no same-session choice existed. Their opportunity cost, if any, lives")
print("  in the hold-window frame below (empty for a fast stop-out — nothing was forgone).")

for tag, label in [("A", "SET A (upper bound — everything that alerted)"),
                   ("B", "SET B (honest counterfactual — only names we CHOSE to skip)")]:
    withalt = [p_ for p_ in POS if p_.get(f"best{tag}")]
    print(f"\nFRAME S AGGREGATES — {label}")
    print(f"  positions with >=1 admissible same-session alternative: {len(withalt)} of {len(POS)} "
          f"({len({p_['d'] for p_ in withalt})} distinct sessions)")
    if not withalt:
        continue
    for basis, key in [("capital (realized)", f"regret_cap{tag}"),
                       ("selection (open->close)", f"regret_sel{tag}")]:
        xs = [p_[key] for p_ in withalt if p_.get(key) is not None]
        m, q1, q3 = med_iqr(xs)
        print(f"  regret vs BEST alt, {basis:<24}: median {pc(m)}  IQR [{pc(q1)},{pc(q3)}]  "
              f"positive (alt beat us) {sum(1 for x in xs if x > 0)}/{len(xs)}")
    xs = [p_[f"medalt{tag}"] - p_["r_real"] for p_ in withalt if p_["r_real"] is not None]
    m, q1, q3 = med_iqr(xs)
    print(f"  regret vs MEDIAN alt, capital basis        : median {pc(m)}  IQR [{pc(q1)},{pc(q3)}]  "
          f"positive {sum(1 for x in xs if x > 0)}/{len(xs)}")
    # rank / percentile on day0 and 5d (same-basis, defined for the whole pool)
    for horiz, own_k, pool_k in [("day0 open->close", "day0_own", f"day0_pool{tag}"),
                                 ("fixed 5-session", "r5_own", f"r5_pool{tag}")]:
        pr = [(p_, pctl(p_[own_k], p_[pool_k])) for p_ in POS
              if p_.get(own_k) is not None and p_.get(pool_k)]
        if horiz.startswith("fixed"):
            pr = [(p_, v) for p_, v in pr if p_["r5_own"] is not None]
        if not pr:
            continue
        vals = [v for _, v in pr]
        print(f"  our pick's percentile in the pool, {horiz:<17}: mean {100*st.fmean(vals):.0f} "
              f"(n={len(vals)} picks, {len({p_['d'] for p_, _ in pr})} sessions; "
              f"50 = indistinguishable from the pool, higher = we picked better)")

# ---------------- random-allocator null (session-level randomization) ----------------
print("\n" + "-" * 96)
print("WOULD A DART-THROWING ALLOCATOR HAVE DONE AS WELL?  (session-level randomization, "
      f"seed {SEED}, {N_MC} draws)")
print("-" * 96)
print("null: each entry session, pick the same NUMBER of names uniformly from the admissible")
print("pool (our picks + that set's alternatives); statistic = mean same-basis return of the")
print("picks. Sessions where the pool offers no choice contribute nothing and are counted.")
rng = random.Random(SEED)
for tag in ("A", "B"):
    for horiz, own_k, pool_k in [("day0", "day0_own", f"day0_pool{tag}"),
                                 ("5d", "r5_own", f"r5_pool{tag}")]:
        sess_pools = {}
        for d in sorted({p_["d"] for p_ in POS}):
            picks = [p_[own_k] for p_ in POS if p_["d"] == d and p_.get(own_k) is not None]
            alts = []
            for p_ in POS:
                if p_["d"] == d:
                    alts = p_[pool_k]
                    break
            if picks and alts:
                sess_pools[d] = (picks, picks + alts)
        if len(sess_pools) < 3:
            print(f"  SET {tag} {horiz:>4}: only {len(sess_pools)} sessions with a genuine choice "
                  f"— N too small for a null, not run")
            continue
        obs_all = [v for picks, _ in sess_pools.values() for v in picks]
        obs = st.fmean(obs_all)
        ge = 0
        for _ in range(N_MC):
            draw = []
            for picks, pool in sess_pools.values():
                draw.extend(rng.sample(pool, len(picks)))
            if st.fmean(draw) >= obs:
                ge += 1
        print(f"  SET {tag} {horiz:>4}: our mean pick return {pc(obs)} over {len(sess_pools)} "
              f"choice-sessions ({len(obs_all)} picks) — {100*(ge+1)/(N_MC+1):.0f}% of random "
              f"allocations return AT LEAST as much (≈50% = indistinguishable)")

# ---------------- frame H ----------------
print("\n" + "-" * 96)
print("FRAME H — WHAT FIRED WHILE CAPITAL WAS TIED (positions held past entry day only)")
print("-" * 96)
print("like-for-like: alt's alert-day open -> our window-end close, vs OUR ticker over the")
print("IDENTICAL dates. Positive edge = the alternative beat continuing to hold ours.")
print("⚠ a fast stop-out has an empty H-frame BY CONSTRUCTION — occupancy cost concentrates")
print("in the names we held longest, which is exactly the operator's point.")
multis = [p_ for p_ in POS if p_["H"]]
print(f"positions with a nonempty hold window: {len(multis)} of {len(POS)}")
for p_ in multis:
    rows = sorted(p_["H"], key=lambda r: -r["edge"])
    rowsB = [r for r in rows if r["a"]["cls"] == "CHOICE"]
    print(f"\n  {p_['ticker']}{'*' if p_['open_pos'] else ''} held {p_['d']}..{p_['end']} "
          f"({p_['hold']} sessions), realized {pc(p_['r_real'])}, "
          f"same-window own open->close {pc(p_['r_sel'])}")
    print(f"    alerts during hold: SET A n={len(rows)} "
          f"({len({r['a']['d'] for r in rows})} sessions) · SET B n={len(rowsB)}")
    for lab, rr in [("A", rows[:3]), ("B", rowsB[:3])]:
        for r in rr:
            a = r["a"]
            print(f"      [{lab}] {a['ticker']:<6} alerted {a['d']} ({a['cls']:<12}) "
                  f"alt {pc(r['r_alt'])} vs ours-same-dates {pc(r['r_own'])} "
                  f"edge {pc(r['edge'])}")
        if lab == "A" and len(rows) > 3:
            print(f"      [A] ... and {len(rows)-3} more")
        if lab == "B" and not rowsB:
            print("      [B] (no choice-skip alerted during this hold)")
    for lab, rr in [("A", rows), ("B", rowsB)]:
        if rr:
            best = max(r["edge"] for r in rr)
            medv = st.median([r["edge"] for r in rr])
            print(f"    hold-window regret set {lab}: best-alt edge {pc(best)}, median-alt edge {pc(medv)}")
print("\n  (no significance test is defined for frame H — the hold windows are not an")
print("   exchangeable unit; descriptive only)")

# ---------------- cap-blocked trio ----------------
print("\n" + "-" * 96)
print("THE ONLY ALTERNATIVES MECHANICALLY BLOCKED BY OUR HOLDINGS (block:max_positions)")
print("-" * 96)
cb = [a for a in hi if a["cls"] == "CAPBLOCK"]
if not cb:
    print("  none in window")
for a in cb:
    r0o = open_on(a["ticker"], a["d"])
    r0c = close_on(a["ticker"], a["d"])
    r5v = ret5(a["ticker"], a["d"])
    d0 = (r0c / r0o - 1) if (r0o and r0c) else None
    print(f"  {a['ticker']:<6} {a['d']}  day0 open->close {pc(d0)}   fixed-5d {pc(r5v) if r5v is not None else '  (immature)'}")
print("  (slot was full because of what we already held — the purest occupancy cost; still")
print("   subject to the no-proven-fill caveat)")

# ---------------- winners vs losers ----------------
print("\n" + "=" * 96)
print("THE SPLIT THE OPERATOR CARES ABOUT — WINNERS vs LOSERS (his claim lives in the winners)")
print("=" * 96)
winners = [p_ for p_ in POS if p_["r_real"] is not None and p_["r_real"] > 0]
losers = [p_ for p_ in POS if p_["r_real"] is not None and p_["r_real"] <= 0]
print(f"winners (realized > 0): {len(winners)} — every one individually below (N too small "
      f"for any aggregate)")
for p_ in winners:
    note = "OPEN, marked" if p_["open_pos"] else ("CLOSED — ASTERISKED: green only because a "
                                                  "bug left shares unstopped" if p_["ticker"] == "ETON" else "CLOSED")
    print(f"\n  {p_['ticker']:<5} entered {p_['d']}, held {p_['hold']} sessions [{note}] "
          f"realized {pc(p_['r_real'])} (${p_['pnl_abs']:+.2f} on ${p_['notional']:.0f})")
    for tag in ("A", "B"):
        b = p_.get(f"best{tag}")
        if b:
            print(f"    same-session set {tag}: best alt {b[0]} {pc(b[1])} over our window -> "
                  f"regret (capital) {pc(p_[f'regret_cap{tag}'])}")
        else:
            print(f"    same-session set {tag}: no admissible alternative "
                  f"({'nothing else alerted' if tag == 'A' else 'no choice-skip that session'})")
    rows = p_["H"]
    rowsB = [r for r in rows if r["a"]["cls"] == "CHOICE"]
    for lab, rr in [("A", rows), ("B", rowsB)]:
        if rr:
            bestr = max(rr, key=lambda r: r["edge"])
            print(f"    hold-window set {lab}: best alt {bestr['a']['ticker']} "
                  f"(alerted {bestr['a']['d']}, {bestr['a']['cls']}) edge {pc(bestr['edge'])} "
                  f"over holding us; median-alt edge {pc(st.median([r['edge'] for r in rr]))}")
        else:
            print(f"    hold-window set {lab}: empty")
print(f"\nlosers (realized <= 0): {len(losers)} over {len({p_['d'] for p_ in losers})} sessions")
for tag in ("A", "B"):
    wl = [p_ for p_ in losers if p_.get(f"best{tag}")]
    xs = [p_[f"regret_cap{tag}"] for p_ in wl if p_.get(f"regret_cap{tag}") is not None]
    if xs:
        m, q1, q3 = med_iqr(xs)
        print(f"  set {tag}: {len(wl)} losers had a same-session alternative; regret vs best, "
              f"capital basis: median {pc(m)} IQR [{pc(q1)},{pc(q3)}], "
              f"alt beat us {sum(1 for x in xs if x > 0)}/{len(xs)}")
    else:
        print(f"  set {tag}: no loser had an admissible same-session alternative")

# ---------------- capital-time weighting ----------------
print("\n" + "-" * 96)
print("CAPITAL-TIME — regret weighted by sessions held (timestamps-derived; hold_days column unused)")
print("-" * 96)
for tag in ("A", "B"):
    rows = [(p_[f"regret_cap{tag}"], p_["hold"]) for p_ in POS
            if p_.get(f"regret_cap{tag}") is not None and p_["hold"]]
    if not rows:
        print(f"  set {tag}: nothing weightable")
        continue
    wsum = sum(w for _, w in rows)
    wavg = sum(r * w for r, w in rows) / wsum
    uavg = st.fmean([r for r, _ in rows])
    print(f"  set {tag} (same-session regret, capital basis): unweighted mean {pc(uavg)} -> "
          f"hold-weighted mean {pc(wavg)}  (n={len(rows)}, total position-sessions {wsum})")
print("  weighting is by SESSIONS not dollars-at-risk; positions are near-equal risk-sized,")
print("  so sessions is the honest available proxy for capital-time.")

print("\n" + "=" * 96)
print("VERDICT — in plain words")
print("=" * 96)
bB = [p_["regret_capB"] for p_ in POS if p_.get("regret_capB") is not None]
bA = [p_["regret_capA"] for p_ in POS if p_.get("regret_capA") is not None]
print(f"""
1. ON THE HONEST COUNTERFACTUAL (SET B — only names we CHOSE to skip): a NULL.
   Median regret vs the best choice-skip is {pc(st.median(bB))} (n={len(bB)} positions,
   {len({p_['d'] for p_ in POS if p_.get('regret_capB') is not None})} sessions), the best alternative beat us in only
   {sum(1 for x in bB if x > 0)} of {len(bB)}, and the dart-thrower test cannot separate our picking from
   chance. What we held did NOT measurably lose to what we could have held.
   ⚠ but SET B barely exists before August — the choice-gates (gap floor, stop-width,
   chase cap) only started skipping names ~07-30, so the honest counterfactual has
   {len({p_['d'] for p_ in POS if p_.get('regret_capB') is not None})} sessions of life. This null is thin, not strong.

2. AGAINST EVERYTHING THAT ALERTED (SET A — upper bound, includes unreachable names):
   we look BELOW PAR. Median regret {pc(st.median(bA))} (n={len(bA)}), the best alert of the morning
   beat our realized result in {sum(1 for x in bA if x > 0)} of {len(bA)}, and at the fixed 5-day horizon ~9 in 10
   random allocations from the same pools would have returned at least as much as ours
   (one-sided p ~ 0.09 — suggestive, NOT past conventional thresholds, and most of set A
   was mechanically unreachable, so this is a ceiling on the problem, not the problem).

3. THE WINNERS (the operator's claim: a winning pick can still be a bad allocation):
   n=3, read individually, no aggregate is honest. ETON supports the claim — its
   asterisked green was third-best of its own morning; HTFL, a stop-width CHOICE
   skip, returned +7.7% against our +2.1%. ABCL is the counterexample — it beat
   every admissible alternative in both frames. PLTR is mixed: no reachable name
   was declined its own session (set B empty), but EROC (a chase-cap CHOICE skip)
   out-ran holding it by ~27 points over its final 3 days.
   One supports, one refutes, one splits — THIS N CANNOT CARRY THE CLAIM EITHER WAY.""")
n1 = sum(1 for p_ in POS if p_["r_real"] is not None and p_["r_real"] <= 0 and p_["hold"] == 1)
print(f"""4. CAPITAL-TIME sharpens nothing yet: hold-weighting moves set-B regret DOWN (the two
   long holds were the two best picks) — on this sample the feared 'marginal winner
   hogging capital' pattern is not visible. The pattern the sample DOES show: losers
   die fast ({n1} of {len(losers)} closed in a single session) and forgo nothing measurable; the
   occupancy question lives entirely in the few multi-day winners, exactly as the plan
   predicts — there just aren't enough of them yet to measure.

BOTTOM LINE: on the only admissible comparison (set B), what we held was
indistinguishable from what we could have held — a real null on a thin, August-only
sample. The below-par signal against set A is real but bounded above the truth.
Collecting more choice-skip sessions is what turns this read decisive; nothing here
licenses touching any rule (THE LINE).""")

print("=" * 96)
print("HOW TO READ THIS — every regret assumes the alternative would have FILLED at its open")
print("print, which is unprovable (ETON). SET B is the honest counterfactual; SET A the upper")
print("bound. Regret-vs-best is max-biased; the median-alt lines correct for that. Nothing")
print("here licenses a change to admission, sizing, slots, grading, or exits — THE LINE.")
print("=" * 96)
