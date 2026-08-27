"""#490 sustain-rule COST — arithmetic over the ONE prod capture (read-only, $0).

Reads scripts/probes/_sustain_cost_capture_out.psv. Writes nothing to prod.

Metric definitions are COPIED FROM THE CANONICAL SOURCES, not re-derived:
  * open_d0 / ret_1d / ret_5d / max_high_5d  -> missed_outcomes.refresh SQL
    (basis = open on the gap day; close_dN = Nth session AFTER d0;
     max_high_5d = MAX(high) over d0..d0+5 inclusive, i.e. LIMIT 6).
  * tailx (the program's tail statistic) -> _552_missed_why_cohort.sql
     adr   = mean((high-low)/close) over the 20 sessions PRECEDING d0
     fwd_hi= max(high) over sessions d0+1 .. d0+20
     tailx = (fwd_hi - close_d0) / close_d0 / adr
    Our window is <=15 sessions deep, so every tailx here is tailx-SO-FAR
    (a FLOOR), exactly as in 490_delayed_screen_cost_2026-08-18.md.
  * outcome freshness -> scanned_report._outcome_is_fresh (the #583 guard).
"""
import statistics as st
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

SEP = "|~|"
PATH = "scripts/probes/_sustain_cost_capture_out.psv"
NOW_ET = datetime(2026, 8, 24, 19, 14, 56, tzinfo=timezone(timedelta(hours=-4)))

RULE_START = date(2026, 8, 3)
ERA_HI_END = date(2026, 8, 7)     # high-supply era (burst week), per the collapse analysis
ERA_LO_START = date(2026, 8, 10)  # low-supply era


def load():
    secs, cur = {}, None
    for line in open(PATH, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("===Q") and line.endswith("==="):
            cur = line.strip("=")
            secs[cur] = []
            continue
        if cur is None or not line or line.startswith("(") and line.endswith("rows)"):
            continue
        secs[cur].append(line.split(SEP))
    out = {}
    for k, rows in secs.items():
        if not rows:
            out[k] = []
            continue
        hdr = rows[0]
        out[k] = [dict(zip(hdr, r)) for r in rows[1:] if len(r) == len(hdr)]
    return out


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def d(x):
    return date.fromisoformat(x) if x else None


S = load()

# ── bars, per ticker, ordered ────────────────────────────────────────────────
bars = defaultdict(list)
for r in S["Q7_DAILY_CLOSES"]:
    bars[r["ticker"]].append((d(r["trade_date"]), f(r["open_price"]), f(r["high_price"]),
                              f(r["low_price"]), f(r["close"]), f(r["volume"])))
for t in bars:
    bars[t].sort()

ALL_SESSIONS = sorted({b[0] for t in bars for b in bars[t]})


def outcome(tkr, d0):
    """Canonical forward metrics for one ticker-day. Returns dict or None."""
    seq = bars.get(tkr)
    if not seq:
        return None
    idx = next((i for i, b in enumerate(seq) if b[0] == d0), None)
    if idx is None:
        return None
    o0, h0, l0, c0 = seq[idx][1], seq[idx][2], seq[idx][3], seq[idx][4]
    if not o0 or o0 <= 0 or not c0 or c0 <= 0:
        return None
    fwd = seq[idx + 1:]
    n_fwd = len(fwd)
    ret_1d = (fwd[0][4] - o0) / o0 if n_fwd >= 1 else None
    ret_5d = (fwd[4][4] - o0) / o0 if n_fwd >= 5 else None
    mh5_bars = seq[idx: idx + 6]                        # d0..d0+5, LIMIT 6
    mh5 = (max(b[2] for b in mh5_bars if b[2]) - o0) / o0
    # tailx-so-far: forward high over d0+1..d0+20, vs close_d0, in own-ADR units
    pre = seq[max(0, idx - 20): idx]
    adr = st.mean([(b[2] - b[3]) / b[4] for b in pre if b[4] and b[2] and b[3]]) if len(pre) >= 5 else None
    fwd20 = fwd[:20]
    fwd_hi = max((b[2] for b in fwd20 if b[2]), default=None)
    tailx = ((fwd_hi - c0) / c0 / adr) if (fwd_hi and adr and adr > 0) else None
    return {"open_d0": o0, "close_d0": c0, "ret_1d": ret_1d, "ret_5d": ret_5d,
            "max_high_5d": mh5, "tailx": tailx, "n_fwd": n_fwd, "adr": adr,
            "settled_5d": n_fwd >= 5, "day_pct": (c0 - o0) / o0}


# ── cohorts, deduped to ticker-day (the audit dedupe is already ticker+date) ──
rej = {(d(r["d_et"]), r["ticker"]): r for r in S["Q2_SUSTAIN_REJECT"] if r["ticker"]}
und = {(d(r["d_et"]), r["ticker"]): r for r in S["Q3_SUSTAIN_UNDECIDABLE"] if r["ticker"]}
cat = {(d(r["d_et"]), r["ticker"]): r for r in S["Q4_UNIVERSE_CATCH"]
       if r["ticker"] and d(r["d_et"]) >= RULE_START}

# a ticker REJECTED at one tick can still be CAUGHT at a later tick the same day:
# the rule only DELAYED it. Net-declined = rejected and never caught that day.
delayed_only = set(rej) & set(cat)
declined = set(rej) - set(cat)

alerts = defaultdict(list)
for r in S["Q5_ALERTS"]:
    if r.get("src", "live") == "live":
        alerts[(d(r["alert_date"]), r["ticker"])].append(r)

scan = {(d(r["scan_date"]), r["ticker"]): r for r in S["Q6_SCANLOG_DEDUPED"]}

mo = {}
for r in S["Q8_MISSED_OUTCOMES"]:
    mo[(d(r["alert_date"]), r["ticker"])] = r


def fresh(row, d0):
    lr = row.get("refreshed_et")
    if not lr:
        return False
    lrt = datetime.fromisoformat(lr).replace(tzinfo=NOW_ET.tzinfo)
    settled_by = datetime(d0.year, d0.month, d0.day, tzinfo=NOW_ET.tzinfo) + timedelta(days=7)
    return lrt >= NOW_ET - timedelta(days=2) or lrt >= settled_by


def era(dd):
    return "high-supply" if dd <= ERA_HI_END else "low-supply"


def describe(keys, label):
    rows = []
    for (dd, tk) in sorted(keys):
        o = outcome(tk, dd)
        rows.append({"d": dd, "t": tk, "era": era(dd), "o": o,
                     "alerted": (dd, tk) in alerts,
                     "scan": scan.get((dd, tk))})
    return label, rows


def stats(rows, key, only_settled=False):
    vals = [r["o"][key] for r in rows
            if r["o"] and r["o"].get(key) is not None
            and (not only_settled or r["o"]["settled_5d"])]
    if not vals:
        return None
    vals.sort()
    return {"n": len(vals), "median": st.median(vals),
            "p90": vals[int(0.9 * (len(vals) - 1))], "max": vals[-1],
            "mean": st.mean(vals)}


def pct(x):
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def block(title, rows):
    print(f"\n### {title}  (n={len(rows)})")
    have = [r for r in rows if r["o"]]
    print(f"  bars available for {len(have)}/{len(rows)}; "
          f"5-session SETTLED {sum(1 for r in have if r['o']['settled_5d'])}, "
          f"CENSORED {sum(1 for r in have if not r['o']['settled_5d'])}")
    print(f"  alerted anyway (live alert same ticker-day): "
          f"{sum(1 for r in rows if r['alerted'])}/{len(rows)}")
    print(f"  reached the delayed scan log that day: "
          f"{sum(1 for r in rows if r['scan'])}/{len(rows)}")
    for k, lbl, settled in [("max_high_5d", "5-session max high vs open", False),
                            ("ret_5d", "5-session close vs open (settled only)", True),
                            ("ret_1d", "next-close vs open", False),
                            ("day_pct", "gap-day open->close", False)]:
        s = stats(have, k, settled)
        if s:
            print(f"  {lbl:<42} n={s['n']:<3} med {pct(s['median']):>8}  "
                  f"P90 {pct(s['p90']):>8}  max {pct(s['max']):>9}")
    tx = [r for r in have if r["o"]["tailx"] is not None]
    if tx:
        v = sorted(r["o"]["tailx"] for r in tx)
        n8 = sum(1 for x in v if x >= 8)
        print(f"  tailx-so-far (ADR units, FLOOR)            n={len(v):<3} "
              f"med {st.median(v):.2f}x  P90 {v[int(0.9*(len(v)-1))]:.2f}x  max {v[-1]:.2f}x"
              f"   >=8xADR: {n8} ({n8/len(v)*100:.1f}%)")
    for thr in (0.20, 0.50, 1.00):
        big = [r for r in have if r["o"]["max_high_5d"] is not None and r["o"]["max_high_5d"] >= thr]
        names = ", ".join(f"{r['t']} {r['d'].strftime('%m-%d')} "
                          f"{r['o']['max_high_5d']*100:+.0f}%"
                          + ("*" if not r["o"]["settled_5d"] else "")
                          + ("[alerted]" if r["alerted"] else "")
                          for r in sorted(big, key=lambda r: -r["o"]["max_high_5d"]))
        print(f"  >= +{thr*100:.0f}% 5-session max high: {len(big)}"
              + (f"  -> {names}" if big else ""))


print("=" * 78)
print("#490 SUSTAIN RULE — WHAT THE DECLINED NAMES DID.  Capture 2026-08-24 19:14 ET")
print("=" * 78)
print("\n## Toggle state read live from mi_safeguard_state")
for r in S["Q1_TOGGLES"]:
    print(f"  {r['safeguard']:<32} {r['state']:<4} since {r['transition_et']}")
print("  ep_rt_universe_authoritative      NO ROW -> defaults False (SHADOW)")
print("  ep_rt_gap_authoritative           NO ROW -> defaults False (SHADOW)")

print("\n## Cohort sizes (ticker-days, deduped)")
print(f"  sustain REJECT events            {len(S['Q2_SUSTAIN_REJECT'])}"
      f"  -> {len(rej)} distinct ticker-days")
print(f"  sustain UNDECIDABLE (fail-OPEN)  {len(S['Q3_SUSTAIN_UNDECIDABLE'])}"
      f"  -> {len(und)} distinct ticker-days")
print(f"  universe CATCH (passed) >=08-03  {len(cat)} distinct ticker-days")
print(f"  rejected then caught later same day (DELAYED, not declined): {len(delayed_only)}")
print(f"  NET DECLINED (rejected, never caught that day):              {len(declined)}")

denom = len(declined) + len(cat)
print(f"\n  decline rate = declined / (declined + passed) = "
      f"{len(declined)}/{denom} = {len(declined)/denom*100:.1f}%")
for lbl, lo, hi in [("high-supply 08-03..08-07", RULE_START, ERA_HI_END),
                    ("low-supply 08-10..08-24", ERA_LO_START, date(2026, 8, 24))]:
    dc = [k for k in declined if lo <= k[0] <= hi]
    pc_ = [k for k in cat if lo <= k[0] <= hi]
    nd = len({k[0] for k in dc} | {k[0] for k in pc_})
    tot = len(dc) + len(pc_)
    print(f"  {lbl:<26} declined {len(dc):>3} / arrivals {tot:>3} = "
          f"{(len(dc)/tot*100 if tot else 0):.1f}%   "
          f"({len(dc)/nd:.1f} declined per trading day over {nd} days)")

print("\n## Per-day")
days = sorted({k[0] for k in set(rej) | set(cat)})
print(f"  {'date':<12}{'declined':>9}{'delayed':>9}{'passed':>8}{'undec':>7}{'alerts':>8}")
for dd in days:
    print(f"  {dd.isoformat():<12}"
          f"{sum(1 for k in declined if k[0]==dd):>9}"
          f"{sum(1 for k in delayed_only if k[0]==dd):>9}"
          f"{sum(1 for k in cat if k[0]==dd):>8}"
          f"{sum(1 for k in und if k[0]==dd):>7}"
          f"{sum(1 for k in alerts if k[0]==dd):>8}")

_, drows = describe(declined, "declined")
_, prows = describe(set(cat), "passed")
_, xrows = describe(delayed_only, "delayed-then-passed")

print("\n" + "=" * 78)
print("## THE COMPARISON — declined vs passed, same days, same basis, same censoring")
print("=" * 78)
block("DECLINED by the sustain rule", drows)
block("PASSED the sustain rule (universe catches)", prows)
if xrows:
    block("REJECTED then CAUGHT later the same day (rule only delayed them)", xrows)

for lbl, lo, hi in [("HIGH-SUPPLY ERA 08-03..08-07", RULE_START, ERA_HI_END),
                    ("LOW-SUPPLY ERA 08-10..08-24", ERA_LO_START, date(2026, 8, 24))]:
    print("\n" + "=" * 78)
    print(f"## {lbl}")
    print("=" * 78)
    block("declined", [r for r in drows if lo <= r["d"] <= hi])
    block("passed", [r for r in prows if lo <= r["d"] <= hi])

print("\n" + "=" * 78)
print("## THE OPERATOR'S PRE-REGISTERED TRIGGER (magna53_ep.md 2026-08-02)")
print('   "a rejected name running >=+20% once is a review, twice a revert"')
print("=" * 78)
hits = [r for r in drows if r["o"] and r["o"]["max_high_5d"] is not None
        and r["o"]["max_high_5d"] >= 0.20]
print(f"  net-declined names reaching >= +20% (5-session max high vs gap-day open): {len(hits)}")
for r in sorted(hits, key=lambda r: -r["o"]["max_high_5d"]):
    a = "ALERTED ANYWAY via the delayed path" if r["alerted"] else "never alerted"
    sc = r["scan"]["filter_reason"] if r["scan"] else "not in scan log"
    print(f"    {r['t']:<6} {r['d']} {r['o']['max_high_5d']*100:+7.1f}%  "
          f"tailx {('%.2fx' % r['o']['tailx']) if r['o']['tailx'] is not None else 'n/a':<7} "
          f"{'SETTLED' if r['o']['settled_5d'] else 'CENSORED'}  {a}  | scan: {sc}")
hits_delayed = [r for r in xrows if r["o"] and r["o"]["max_high_5d"] is not None
                and r["o"]["max_high_5d"] >= 0.20]
print(f"\n  (for reference, rejected-then-caught names >= +20%: {len(hits_delayed)} — "
      f"these were NOT declined)")
for r in sorted(hits_delayed, key=lambda r: -r["o"]["max_high_5d"]):
    print(f"    {r['t']:<6} {r['d']} {r['o']['max_high_5d']*100:+7.1f}%")

print("\n" + "=" * 78)
print("## COVERAGE / CENSORING")
print("=" * 78)
nb = [r for r in drows if not r["o"]]
print(f"  declined ticker-days with NO daily bar at all: {len(nb)}"
      + (f" -> {', '.join(r['t'] + ' ' + r['d'].strftime('%m-%d') for r in nb)}" if nb else ""))
print(f"  last session in mi_daily_closes: {ALL_SESSIONS[-1] if ALL_SESSIONS else 'n/a'}")
fresh_mo = sum(1 for (dd, tk) in declined if (dd, tk) in mo and fresh(mo[(dd, tk)], dd))
print(f"  declined ticker-days present in mi_ep_missed_outcomes with a FRESH row "
      f"(#583 guard): {fresh_mo}/{len(declined)}")
fresh_mo_p = sum(1 for (dd, tk) in cat if (dd, tk) in mo and fresh(mo[(dd, tk)], dd))
print(f"  passed   ticker-days present in mi_ep_missed_outcomes with a FRESH row: "
      f"{fresh_mo_p}/{len(cat)}")

print("\n## Cross-check: mi_daily_closes vs mi_ep_missed_outcomes where BOTH exist and are fresh")
diffs = []
for (dd, tk) in sorted(set(declined) | set(cat)):
    row = mo.get((dd, tk))
    if not row or not fresh(row, dd):
        continue
    o = outcome(tk, dd)
    a, b = f(row.get("max_high_5d")), (o or {}).get("max_high_5d")
    if a is not None and b is not None:
        diffs.append(abs(a - b))
if diffs:
    print(f"  n={len(diffs)}  max abs difference in max_high_5d: {max(diffs)*100:.3f} pp "
          f"(median {st.median(diffs)*100:.3f} pp)")
else:
    print("  no overlapping fresh rows to cross-check")

print("\n" + "=" * 78)
print("## THE TAIL — every name reaching >=8xADR (the program's tail-winner bar)")
print("=" * 78)
for lbl, rows in [("DECLINED", drows), ("PASSED", prows), ("DELAYED-THEN-PASSED", xrows)]:
    tw = [r for r in rows if r["o"] and r["o"]["tailx"] is not None and r["o"]["tailx"] >= 8]
    nn = len([r for r in rows if r["o"] and r["o"]["tailx"] is not None])
    print(f"  {lbl:<22} {len(tw)}/{nn} ({len(tw)/nn*100:.1f}%)")
    for r in sorted(tw, key=lambda r: -r["o"]["tailx"]):
        sc = r["scan"]["filter_reason"] if r["scan"] else "not in scan log"
        print(f"      {r['t']:<6} {r['d']}  tailx {r['o']['tailx']:.2f}x  "
              f"5d max high {r['o']['max_high_5d']*100:+.1f}%  "
              f"fwd sessions {r['o']['n_fwd']}  | scan: {sc[:60]}")


def fisher(a, b, c, dd):
    """two-sided Fisher exact p for [[a,b],[c,d]] — pure stdlib."""
    from math import comb
    n = a + b + c + dd
    r1, c1 = a + b, a + c

    def p(x):
        return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    p0 = p(a)
    lo = max(0, c1 - (n - r1))
    hi = min(r1, c1)
    return sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 * 1.0000001)


dt = [r for r in drows if r["o"] and r["o"]["tailx"] is not None]
pt = [r for r in prows if r["o"] and r["o"]["tailx"] is not None]
a = sum(1 for r in dt if r["o"]["tailx"] >= 8)
c = sum(1 for r in pt if r["o"]["tailx"] >= 8)
print(f"\n  >=8xADR density: declined {a}/{len(dt)} vs passed {c}/{len(pt)} — "
      f"two-sided Fisher exact p = {fisher(a, len(dt)-a, c, len(pt)-c):.3f}")
a2 = sum(1 for r in drows if r["o"] and r["o"]["max_high_5d"] >= 0.20)
c2 = sum(1 for r in prows if r["o"] and r["o"]["max_high_5d"] >= 0.20)
print(f"  >=+20% density:  declined {a2}/{len(drows)} vs passed {c2}/{len(prows)} — "
      f"p = {fisher(a2, len(drows)-a2, c2, len(prows)-c2):.3f}")

print("\n" + "=" * 78)
print("## DECLINE RATE — every denominator, so the '1 in 7 -> 1 in 3' claim is checkable")
print("=" * 78)
weeks = [("08-03..08-07", date(2026, 8, 3), date(2026, 8, 7)),
         ("08-10..08-14", date(2026, 8, 10), date(2026, 8, 14)),
         ("08-17..08-21", date(2026, 8, 17), date(2026, 8, 21)),
         ("08-24 (1 day)", date(2026, 8, 24), date(2026, 8, 24))]
print(f"  {'week':<15}{'rejects':>8}{'declined':>9}{'delayed':>8}{'passed':>7}{'undec':>6}"
      f"{'rej/arrivals':>13}{'declined/arr':>13}")
for lbl, lo, hi in weeks:
    R = [k for k in rej if lo <= k[0] <= hi]
    D = [k for k in declined if lo <= k[0] <= hi]
    X = [k for k in delayed_only if lo <= k[0] <= hi]
    P = [k for k in cat if lo <= k[0] <= hi]
    U = [k for k in und if lo <= k[0] <= hi]
    arr_raw = len(R) + len(P) + len(U)      # everything that reached the gate
    arr_net = len(D) + len(P) + len(U)      # net of names the rule merely delayed
    print(f"  {lbl:<15}{len(R):>8}{len(D):>9}{len(X):>8}{len(P):>7}{len(U):>6}"
          f"{len(R)/arr_raw*100:>12.1f}%{len(D)/arr_net*100:>12.1f}%")
print("  arrivals = rejects + passed + undecidable (undecidable FAILS OPEN = admitted)")

print("\n" + "=" * 78)
print("## THE 2026-08-02 REPLAY'S OWN PREDICTION vs LIVE (pre-committed watch item)")
print("   replay, N=97 catches 07-27..08-02: 3-consecutive ADMITS med open->close +5.0%,")
print("   win>=+5% 50%; the unfiltered 1-bar pool was +3.9% / 41%.")
print("=" * 78)
for lbl, rows in [("live ADMITS (passed)", prows), ("live DECLINES", drows),
                  ("live delayed-then-passed", xrows)]:
    v = [r["o"]["day_pct"] for r in rows if r["o"]]
    w = sum(1 for x in v if x >= 0.05)
    print(f"  {lbl:<26} n={len(v):<4} med open->close {st.median(v)*100:+5.1f}%   "
          f"win>=+5% {w}/{len(v)} = {w/len(v)*100:.0f}%")
allc = [r["o"]["day_pct"] for r in (prows + drows + xrows) if r["o"]]
wa = sum(1 for x in allc if x >= 0.05)
print(f"  {'rule OFF (all arrivals)':<26} n={len(allc):<4} med open->close "
      f"{st.median(allc)*100:+5.1f}%   win>=+5% {wa}/{len(allc)} = {wa/len(allc)*100:.0f}%")

print("\n## Censoring-matched (5-session SETTLED rows only, both cohorts)")
for lbl, rows in [("declined", drows), ("passed", prows)]:
    s = [r for r in rows if r["o"] and r["o"]["settled_5d"]]
    mh = sorted(r["o"]["max_high_5d"] for r in s)
    r5 = sorted(r["o"]["ret_5d"] for r in s)
    n20 = sum(1 for x in mh if x >= 0.20)
    print(f"  {lbl:<10} n={len(s):<4} 5d max high med {st.median(mh)*100:+5.1f}% "
          f"P90 {mh[int(0.9*(len(mh)-1))]*100:+6.1f}% max {mh[-1]*100:+7.1f}%   "
          f">=+20% {n20}/{len(s)} = {n20/len(s)*100:.0f}%   "
          f"5d close med {st.median(r5)*100:+5.1f}%")

ds = [r for r in drows if r["o"] and r["o"]["settled_5d"]]
ps = [r for r in prows if r["o"] and r["o"]["settled_5d"]]
a3 = sum(1 for r in ds if r["o"]["max_high_5d"] >= 0.20)
c3 = sum(1 for r in ps if r["o"]["max_high_5d"] >= 0.20)
print(f"\n  SETTLED-only >=+20%: declined {a3}/{len(ds)} vs passed {c3}/{len(ps)} — "
      f"two-sided Fisher exact p = {fisher(a3, len(ds)-a3, c3, len(ps)-c3):.4f}")
print("  era mix of the settled rows: "
      f"declined {sum(1 for r in ds if r['era']=='high-supply')}/{len(ds)} high-supply, "
      f"passed {sum(1 for r in ps if r['era']=='high-supply')}/{len(ps)} high-supply")
for lbl, lo, hi in [("high-supply", RULE_START, ERA_HI_END),
                    ("low-supply", ERA_LO_START, date(2026, 8, 24))]:
    dd_ = [r for r in ds if lo <= r["d"] <= hi]
    pp_ = [r for r in ps if lo <= r["d"] <= hi]
    if dd_ and pp_:
        ad = sum(1 for r in dd_ if r["o"]["max_high_5d"] >= 0.20)
        ap = sum(1 for r in pp_ if r["o"]["max_high_5d"] >= 0.20)
        print(f"    {lbl:<12} declined {ad}/{len(dd_)} = {ad/len(dd_)*100:.0f}%   "
              f"passed {ap}/{len(pp_)} = {ap/len(pp_)*100:.0f}%   "
              f"| 5d max high med: declined {st.median([r['o']['max_high_5d'] for r in dd_])*100:+.1f}% "
              f"vs passed {st.median([r['o']['max_high_5d'] for r in pp_])*100:+.1f}%")

print("\n" + "=" * 78)
print("## MECHANISM — what shape of tape does the rule actually decline?")
print("   _sustain_ok reads the last 3 minute closes OLDEST->NEWEST and rejects unless")
print("   ALL THREE sit at or above the gap floor.")
print("=" * 78)
import json as _json
shapes = defaultdict(list)
for (dd, tk) in sorted(declined):
    try:
        det = _json.loads(rej[(dd, tk)]["detail_json"])
    except Exception:
        continue
    g = det.get("gaps")
    if not g or len(g) < 2:
        continue
    if g[-1] == max(g) and g[-1] > g[0]:
        s = "RISING into the level (newest bar is the high)"
    elif g[-1] < g[0]:
        s = "FADING off the level (newest bar below the oldest)"
    else:
        s = "flat / mixed"
    o = outcome(tk, dd)
    shapes[s].append((tk, dd, g, o))
tot = sum(len(v) for v in shapes.values())
for s, v in sorted(shapes.items(), key=lambda kv: -len(kv[1])):
    mh = [x[3]["max_high_5d"] for x in v if x[3]]
    n20 = sum(1 for x in mh if x >= 0.20)
    print(f"  {s:<46} {len(v):>3}/{tot} ({len(v)/tot*100:.0f}%)"
          + (f"   5d max high med {st.median(mh)*100:+.1f}%, >=+20% {n20}" if mh else ""))
print("\n  examples of the RISING class (the operator's premise was a FADING spike):")
for tk, dd, g, o in shapes["RISING into the level (newest bar is the high)"][:8]:
    print(f"    {tk:<6} {dd}  bar closes as % gap: {g}"
          + (f"   -> 5d max high {o['max_high_5d']*100:+.1f}%" if o else ""))

print("\n" + "=" * 78)
print("## UPPER BOUND — declined names never faced the downstream gates.")
print("   Any scan-log row for the same TICKER anywhere in 08-01..08-24 that names a")
print("   STRUCTURAL disqualifier (market cap / ADV / extension) applies to the name,")
print("   not just to that date.")
print("=" * 78)
struct = defaultdict(list)
for r in S["Q6_SCANLOG_DEDUPED"]:
    fr = r["filter_reason"] or ""
    for key in ("mcap_too_small", "adv_too_low", "extended", "dollar_vol"):
        if key in fr:
            struct[r["ticker"]].append((r["scan_date"], fr))
top = [r for r in drows if r["o"] and r["o"]["max_high_5d"] is not None
       and r["o"]["max_high_5d"] >= 0.20]
blocked = [r for r in top if r["t"] in struct]
print(f"  of the {len(top)} declined names reaching >=+20%, {len(blocked)} carry a recorded "
      f"structural disqualifier elsewhere in the window:")
for r in sorted(blocked, key=lambda r: -r["o"]["max_high_5d"]):
    dd_, fr = struct[r["t"]][0]
    print(f"    {r['t']:<6} {r['d']} {r['o']['max_high_5d']*100:+6.1f}%  ->  {fr[:90]}")
tw = [r for r in drows if r["o"] and r["o"]["tailx"] is not None and r["o"]["tailx"] >= 8]
print(f"\n  of the {len(tw)} declined names reaching >=8xADR:")
for r in sorted(tw, key=lambda r: -r["o"]["tailx"]):
    fr = struct[r["t"]][0][1][:90] if r["t"] in struct else "NO recorded structural block"
    print(f"    {r['t']:<6} {r['d']}  {r['o']['tailx']:.1f}xADR  ->  {fr}")

print("\n" + "=" * 78)
print("## CONTROL — did the level actually HOLD at the open?")
print("   gap_at_open = (open_d0 - prior session close) / prior session close,")
print("   against the floor in force that day (10.0% through 08-19, 9.0% from 08-20).")
print("   A declined name that opens BELOW the floor is a print that never became a")
print("   level: the rule was right, and its lower open_d0 mechanically INFLATES")
print("   max_high_5d/open_d0 relative to a name that held and opened high.")
print("=" * 78)


def floor_on(dd):
    return 10.0 if dd < date(2026, 8, 20) else 9.0


def gap_open(tkr, d0):
    seq = bars.get(tkr) or []
    i = next((j for j, b in enumerate(seq) if b[0] == d0), None)
    if i is None or i == 0:
        return None
    pc, o = seq[i - 1][4], seq[i][1]
    return None if not pc or pc <= 0 or not o else (o - pc) / pc * 100


for r in drows + prows + xrows:
    r["gopen"] = gap_open(r["t"], r["d"])
    r["held"] = (r["gopen"] is not None and r["gopen"] >= floor_on(r["d"]))

for lbl, rows in [("DECLINED", drows), ("PASSED", prows), ("DELAYED-THEN-PASSED", xrows)]:
    hv = [r for r in rows if r["gopen"] is not None]
    h = [r for r in hv if r["held"]]
    print(f"  {lbl:<22} held the floor at the open: {len(h)}/{len(hv)} = "
          f"{len(h)/len(hv)*100:.0f}%   median gap at open "
          f"{st.median([r['gopen'] for r in hv]):+.1f}%")

print("\n## Re-run of Result 3 INSIDE the held-at-open subset (settled rows only)")
for lbl, rows in [("declined", drows), ("passed", prows)]:
    s = [r for r in rows if r["held"] and r["o"] and r["o"]["settled_5d"]]
    if not s:
        print(f"  {lbl:<10} n=0")
        continue
    mh = sorted(r["o"]["max_high_5d"] for r in s)
    n20 = sum(1 for x in mh if x >= 0.20)
    tx = [r["o"]["tailx"] for r in s if r["o"]["tailx"] is not None]
    n8 = sum(1 for x in tx if x >= 8)
    print(f"  {lbl:<10} n={len(s):<4} 5d max high med {st.median(mh)*100:+5.1f}%  "
          f">=+20% {n20}/{len(s)} = {n20/len(s)*100:.0f}%   "
          f">=8xADR {n8}/{len(tx)}   "
          f"5d close med {st.median([r['o']['ret_5d'] for r in s])*100:+5.1f}%")
ds2 = [r for r in drows if r["held"] and r["o"] and r["o"]["settled_5d"]]
ps2 = [r for r in prows if r["held"] and r["o"] and r["o"]["settled_5d"]]
if ds2 and ps2:
    a4 = sum(1 for r in ds2 if r["o"]["max_high_5d"] >= 0.20)
    c4 = sum(1 for r in ps2 if r["o"]["max_high_5d"] >= 0.20)
    print(f"  held-at-open settled >=+20%: declined {a4}/{len(ds2)} vs passed {c4}/{len(ps2)} — "
          f"two-sided Fisher exact p = {fisher(a4, len(ds2)-a4, c4, len(ps2)-c4):.3f}")

print("\n## Re-run of Result 3 on ALL held-at-open rows (censored included)")
for lbl, rows in [("declined", drows), ("passed", prows)]:
    s = [r for r in rows if r["held"] and r["o"]]
    if not s:
        continue
    mh = sorted(r["o"]["max_high_5d"] for r in s)
    n20 = sum(1 for x in mh if x >= 0.20)
    print(f"  {lbl:<10} n={len(s):<4} 5d max high med {st.median(mh)*100:+5.1f}%  "
          f">=+20% {n20}/{len(s)} = {n20/len(s)*100:.0f}%")

print("\n## Result 5 re-stated under the control")
tw = [r for r in drows if r["o"] and r["o"]["tailx"] is not None and r["o"]["tailx"] >= 8]
for r in sorted(tw, key=lambda x: -x["o"]["tailx"]):
    print(f"  DECLINED {r['t']:<6} {r['d']} {r['o']['tailx']:.1f}xADR  gap at open "
          f"{r['gopen']:+.1f}% vs floor {floor_on(r['d']):.0f}%  -> "
          f"{'HELD' if r['held'] else 'DID NOT HOLD — the rule was right'}")
tp = [r for r in prows if r["o"] and r["o"]["tailx"] is not None and r["o"]["tailx"] >= 8]
for r in sorted(tp, key=lambda x: -x["o"]["tailx"]):
    print(f"  PASSED   {r['t']:<6} {r['d']} {r['o']['tailx']:.1f}xADR  gap at open "
          f"{r['gopen']:+.1f}% vs floor {floor_on(r['d']):.0f}%  -> "
          f"{'HELD' if r['held'] else 'DID NOT HOLD'}")

print("\n## The 20 declined names >=+20%, under the control")
top = [r for r in drows if r["o"] and r["o"]["max_high_5d"] >= 0.20]
held_top = [r for r in top if r["held"]]
print(f"  held the floor at the open: {len(held_top)}/{len(top)}")
for r in sorted(top, key=lambda x: -x["o"]["max_high_5d"]):
    print(f"    {r['t']:<6} {r['d']} {r['o']['max_high_5d']*100:+6.1f}%  open gap "
          f"{r['gopen']:+6.1f}%  {'HELD' if r['held'] else 'faded'}")

print("\n## Result 7 Arm 2 recomputed with undecidables in BOTH sides")
und_rows = []
for (dd, tk) in sorted(und):
    o = outcome(tk, dd)
    if o:
        und_rows.append({"o": o})
adm = [r for r in prows if r["o"]] + und_rows           # rule ON  = passed + undecidable
off = adm + [r for r in drows if r["o"]]                # rule OFF = everything that arrived
for lbl, rows in [("rule ON  (admitted)", adm), ("rule OFF (all arrivals)", off)]:
    v = [r["o"]["day_pct"] for r in rows]
    w = sum(1 for x in v if x >= 0.05)
    print(f"  {lbl:<26} n={len(v):<4} med open->close {st.median(v)*100:+5.1f}%   "
          f"win>=+5% {w}/{len(v)} = {w/len(v)*100:.0f}%")

print("\n" + "=" * 78)
print("## THE BOTTOM LINE — declines that BOTH held the floor at the open AND ran")
print("=" * 78)
cand = [r for r in drows if r["held"] and r["o"] and r["o"]["max_high_5d"] >= 0.20]
print(f"  candidates for a real cost: {len(cand)}")
for r in sorted(cand, key=lambda x: -x["o"]["max_high_5d"]):
    sc = r["scan"]["filter_reason"] if r["scan"] else "never reached the scan log"
    other = struct.get(r["t"])
    print(f"    {r['t']:<6} {r['d']}  open gap {r['gopen']:+.1f}%  5d max high "
          f"{r['o']['max_high_5d']*100:+.1f}%  tailx "
          f"{('%.1fx' % r['o']['tailx']) if r['o']['tailx'] is not None else 'n/a'}")
    print(f"           alerted anyway: {'YES' if r['alerted'] else 'no'}   "
          f"scan log that day: {sc[:70]}")
    if other:
        print(f"           structural block elsewhere: {other[0][1][:70]}")
print("\n  same filter applied to the PASSED cohort (held at open AND ran >=+20%): "
      f"{len([r for r in prows if r['held'] and r['o'] and r['o']['max_high_5d'] >= 0.20])}")

print("\n## Mechanism reconciled with the control — did the RISING names hold at the open?")
for s, v in sorted(shapes.items(), key=lambda kv: -len(kv[1])):
    ks = {(x[1], x[0]) for x in v}
    rs = [r for r in drows if (r["d"], r["t"]) in ks]
    h = [r for r in rs if r["held"]]
    print(f"  {s:<46} {len(h)}/{len(rs)} held the floor at the open "
          f"({len(h)/len(rs)*100:.0f}%)")
