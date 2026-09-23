"""Pivot proximity — sizing the 'approached but never touched' population. (2026-08-16)

Operator's entry architecture (docs/setups/delayed_ep_reentry.md §2026-08-16): a ladder of
pivots fixed at the EP event (EP-day LOW / CLOSE / HIGH), and PROXIMITY-not-touch — when
price closes in on a pivot we go to the intraday chart (620) and take a turn NEAR it.
Every rule modelled so far requires a TOUCH. INTC 2026-04-24 is the proof case: a limit at
the EP-day low ($79.62) never filled — bottom $80.80, 1.5% above — and the name ran +14R.

THIS PROBE SIZES THE NEAR-MISS POPULATION. For each of the 99 cohort names (HIGH-tier EP
alerts with 60 forward sessions, the _delayed_reentry cohort), for each pivot, over the
next 10 and 20 sessions:
  TOUCHED          a daily low <= the pivot
  NEAR-MISS        never touched, min low within BAND x ADR20 of the pivot (0.25 / 0.5)
  NEVER APPROACHED min low stayed above pivot + band

Outcomes over the full 60-session horizon, in ADR units:
  touched    : entry AT the pivot on the touch day; MFE from the NEXT day (daily-bar
               convention of _delayed_reentry.run — the touch day's own high is not
               orderable vs its low at this resolution)
  near-miss  : priced BOTH at the pivot (what a limit forfeits) and at the closest
               approach (what a proximity entry would actually pay); MFE from the day
               after the closest approach
  never      : excursion from the pivot over the whole horizon — CONTEXT ONLY, no entry
               at/near this pivot could have captured it

ADR20 = mean (high-low)/close over the 20 sessions BEFORE the EP day (the established
_delayed_reentry_v2 / _306 definition). ADR-dollars anchored at the entry price used.

⚠ Daily-bar resolution: we measure the APPROACH, not whether a 620 turn actually fired
there — this sizes the opportunity, not the yield. 🛑 THE LINE: measured only; no rule,
no threshold proposed.
"""
from collections import defaultdict
from pathlib import Path
import statistics as st
import _468_moderate_realized_r as M

H = Path(".").resolve()
M.COHORT, M.DAILY = H / "_468_cohort.tsv", H / "_468_daily_full.tsv"
HORIZON = 60
WINDOWS = (10, 20)
BANDS = (0.25, 0.5)
BIG_ADR = 8.0            # the tail-winner bar used across this program

def adr20_frac(db, i):
    w = db[max(0, i - 20):i]
    return (sum((b["h"] - b["l"]) / b["c"] for b in w if b["c"]) / len(w)) if w else None

rows = [r for r in M.load_cohort() if r["tier"] == "HIGH"]
daily = M.load_daily()
names = []
for r in rows:
    db = daily.get(r["ticker"], [])
    i = M.idx_of_date(db, r["alert_date"])
    if i is None or len(db) - i - 1 < HORIZON:
        continue
    a = adr20_frac(db, i)
    if not a or a <= 0:
        continue
    ep = db[i]
    names.append(dict(nm=f"{r['ticker']} {r['alert_date']}", date=r["alert_date"],
                      ep=ep, fwd=db[i + 1:i + 1 + HORIZON], adr=a,
                      gap=r["gap_pct"], score=r["ep_score"]))

print(f"cohort: {len(names)} names ({len({n['date'] for n in names})} distinct sessions) "
      f"— HIGH-tier EP alerts with {HORIZON} forward sessions (the _delayed_reentry cohort)")
print(f"median ADR20 of the cohort: {st.median(n['adr'] for n in names)*100:.2f}% of price\n")

PIVOTS = [("EP-day LOW", lambda ep: ep["l"]),
          ("EP-day CLOSE", lambda ep: ep["c"]),
          ("EP-day HIGH", lambda ep: ep["h"])]


def classify(n, P, W, B):
    """-> dict(cls, and per-class fields). Approach semantics: from above, on daily lows."""
    adr_d = n["adr"] * P                      # ADR-dollars at the pivot
    win = n["fwd"][:W]
    lows = [d["l"] for d in win]
    minlow = min(lows)
    j_touch = next((j for j, d in enumerate(win) if d["l"] <= P), None)
    if j_touch is not None:
        rest = n["fwd"][j_touch + 1:]
        mfe = max((d["h"] for d in rest), default=P)
        return dict(cls="touched", j=j_touch, exc_pivot=(mfe - P) / adr_d)
    dist = (minlow - P) / adr_d
    if dist <= B:
        j_app = lows.index(minlow)            # first day of the closest approach
        rest = n["fwd"][j_app + 1:]
        mfe = max((d["h"] for d in rest), default=minlow)
        return dict(cls="near", j=j_app, dist=dist, appr=minlow,
                    exc_pivot=(mfe - P) / adr_d,
                    exc_appr=(mfe - minlow) / (n["adr"] * minlow))
    mfe = max((d["h"] for d in n["fwd"]), default=P)
    return dict(cls="never", exc_pivot=(mfe - P) / adr_d)


def fmt_stats(xs, big):
    if not xs:
        return "n=0"
    return (f"med {st.median(xs):+6.1f}  mean {sum(xs)/len(xs):+6.1f}  "
            f"max {max(xs):+6.1f}  >= {BIG_ADR:.0f}xADR: {sum(1 for x in xs if x >= big)}"
            f"/{len(xs)} ({100*sum(1 for x in xs if x >= big)/len(xs):.0f}%)")


def sess(rows_):
    return len({r['date'] for r in rows_})


results = {}      # (pivot, W, B) -> list of (name-dict, class-dict)
for pname, pf in PIVOTS:
    for W in WINDOWS:
        for B in BANDS:
            out = []
            for n in names:
                out.append((n, classify(n, pf(n["ep"]), W, B)))
            results[(pname, W, B)] = out

# ── 1. the split, per pivot / window / band ─────────────────────────────────
print("=" * 100)
print("1) TOUCHED / NEAR-MISS / NEVER-APPROACHED — per pivot, window, band "
      "(N + distinct sessions on every line)")
print("=" * 100)
for pname, _ in PIVOTS:
    for W in WINDOWS:
        for B in BANDS:
            out = results[(pname, W, B)]
            t = [(n, c) for n, c in out if c["cls"] == "touched"]
            nm = [(n, c) for n, c in out if c["cls"] == "near"]
            nv = [(n, c) for n, c in out if c["cls"] == "never"]
            print(f"\n{pname:<14} window {W:>2}d  band {B:.2f}xADR20   "
                  f"touched {len(t)} ({sess([n for n,_ in t])} sess) | "
                  f"near-miss {len(nm)} ({sess([n for n,_ in nm])} sess) | "
                  f"never {len(nv)} ({sess([n for n,_ in nv])} sess)")
            print(f"   touched   — entry AT pivot        : "
                  f"{fmt_stats([c['exc_pivot'] for _, c in t], BIG_ADR)}")
            print(f"   near-miss — priced at PIVOT (forfeited by a hard limit): "
                  f"{fmt_stats([c['exc_pivot'] for _, c in nm], BIG_ADR)}")
            print(f"   near-miss — priced at CLOSEST APPROACH (what proximity pays): "
                  f"{fmt_stats([c['exc_appr'] for _, c in nm], BIG_ADR)}")
            print(f"   never     — from pivot, NOT capturable by this pivot : "
                  f"{fmt_stats([c['exc_pivot'] for _, c in nv], BIG_ADR)}")

# ── 2. the headline: >=8xADR opportunity sitting in NEAR-MISS ───────────────
print("\n" + "=" * 100)
print(f"2) HEADLINE — >= {BIG_ADR:.0f}xADR winners by class (winner counts; "
      "near-miss priced at the closest approach)")
print("=" * 100)
print(f"{'pivot':<14}{'win':>4}{'band':>6}{'touched>=8':>12}{'near>=8':>9}"
      f"{'never>=8*':>10}   near-miss >=8xADR names (exc at approach)")
for pname, _ in PIVOTS:
    for W in WINDOWS:
        for B in BANDS:
            out = results[(pname, W, B)]
            tb = [(n, c) for n, c in out if c["cls"] == "touched" and c["exc_pivot"] >= BIG_ADR]
            nb = [(n, c) for n, c in out if c["cls"] == "near" and c["exc_appr"] >= BIG_ADR]
            vb = [(n, c) for n, c in out if c["cls"] == "never" and c["exc_pivot"] >= BIG_ADR]
            lst = ", ".join(f"{n['nm']} ({c['exc_appr']:+.1f})" for n, c in
                            sorted(nb, key=lambda x: -x[1]["exc_appr"]))
            print(f"{pname:<14}{W:>4}{B:>6.2f}{len(tb):>12}{len(nb):>9}{len(vb):>10}   {lst}")
print("* never-approached >=8xADR = names that ran without ever coming near this pivot — "
      "no entry at/near it existed")

# ── 3. the LADDER view: names NO pivot touched, but >=1 pivot near-missed ───
print("\n" + "=" * 100)
print("3) LADDER VIEW — names where a hard limit at EVERY pivot fails, but a proximity "
      "band catches at least one pivot")
print("   (pivots are nested low<close<high, so 'touched none' = never touched EP-day HIGH)")
print("=" * 100)
for W in WINDOWS:
    for B in BANDS:
        rows_ = []
        for k, n in enumerate(names):
            per = {p: results[(p, W, B)][k][1] for p, _ in PIVOTS}
            if any(c["cls"] == "touched" for c in per.values()):
                continue
            nears = {p: c for p, c in per.items() if c["cls"] == "near"}
            if not nears:
                continue
            bp, bc = max(nears.items(), key=lambda x: x[1]["exc_appr"])
            rows_.append((n, bp, bc))
        big = [r for r in rows_ if r[2]["exc_appr"] >= BIG_ADR]
        print(f"\nwindow {W}d band {B:.2f}: {len(rows_)} names "
              f"({sess([n for n, _, _ in rows_])} sess) fully forfeited by the whole "
              f"hard-limit ladder yet inside a proximity band; of them >= {BIG_ADR:.0f}xADR: {len(big)}")
        for n, bp, bc in sorted(rows_, key=lambda r: -r[2]["exc_appr"]):
            print(f"   {n['nm']:<22} best band pivot {bp:<13} approach "
                  f"{bc['dist']:.2f}xADR away on day {bc['j']+1:>2} -> "
                  f"{bc['exc_appr']:+6.1f}xADR from the approach")

# ── 4. near-miss ran vs died — anything distinguishing? ─────────────────────
print("\n" + "=" * 100)
print("4) NEAR-MISS: RAN vs DIED — per-name features (window 20d, band 0.50 — the widest "
      "set; LOW and CLOSE pivots, the two he named)")
print("   ran = >= 8xADR from the approach; died = < 2xADR; middle shown unlabelled")
print("=" * 100)
for pname in ("EP-day LOW", "EP-day CLOSE"):
    out = results[(pname, 20, 0.5)]
    nm = [(n, c) for n, c in out if c["cls"] == "near"]
    print(f"\n{pname} — {len(nm)} near-misses ({sess([n for n,_ in nm])} sessions)")
    print(f"   {'name':<22}{'label':<7}{'excADR':>7}{'gap%':>7}{'ADR%':>6}"
          f"{'distADR':>8}{'day':>4}")
    for n, c in sorted(nm, key=lambda x: -x[1]["exc_appr"]):
        lab = "RAN" if c["exc_appr"] >= BIG_ADR else ("died" if c["exc_appr"] < 2 else "")
        print(f"   {n['nm']:<22}{lab:<7}{c['exc_appr']:>+7.1f}{(n['gap'] or 0):>7.1f}"
              f"{n['adr']*100:>6.2f}{c['dist']:>8.2f}{c['j']+1:>4}")
    ran = [(n, c) for n, c in nm if c["exc_appr"] >= BIG_ADR]
    died = [(n, c) for n, c in nm if c["exc_appr"] < 2]
    for lab, grp in (("RAN", ran), ("died", died)):
        if grp:
            print(f"   {lab:<5} n={len(grp)}  med gap {st.median((n['gap'] or 0) for n, _ in grp):.1f}%  "
                  f"med ADR {st.median(n['adr'] for n, _ in grp)*100:.2f}%  "
                  f"med dist {st.median(c['dist'] for _, c in grp):.2f}xADR  "
                  f"med day {st.median(c['j']+1 for _, c in grp):.0f}")

# ── sanity: the INTC proof case ─────────────────────────────────────────────
print("\n" + "=" * 100)
print("SANITY — INTC 2026-04-24 (the proof case)")
print("=" * 100)
k = next(i for i, n in enumerate(names) if n["nm"] == "INTC 2026-04-24")
n = names[k]
for pname, pf in PIVOTS:
    c = results[(pname, 20, 0.5)][k][1]
    extra = (f" dist {c['dist']:.2f}xADR appr {c['appr']:.2f}" if c["cls"] == "near" else
             (f" touch day {c['j']+1}" if c["cls"] == "touched" else ""))
    print(f"   {pname:<14} pivot {pf(n['ep']):>8.2f}  -> {c['cls']:<8}{extra}  "
          f"exc_pivot {c['exc_pivot']:+.1f}xADR"
          + (f"  exc_appr {c['exc_appr']:+.1f}xADR" if c["cls"] == "near" else ""))
print(f"   (EP low 79.62 / close {n['ep']['c']:.2f} / high {n['ep']['h']:.2f}; "
      f"ADR20 {n['adr']*100:.2f}% = ${n['adr']*n['ep']['l']:.2f} at the low pivot)")

# ── 5. dynamics that qualify the headline ───────────────────────────────────
print("\n" + "=" * 100)
print("5a) PATIENCE vs PROXIMITY — near-misses at 10d: do they touch if you wait?")
print("=" * 100)
for B in BANDS:
    out10 = results[("EP-day LOW", 10, B)]
    nm10 = [(k, n, c) for k, (n, c) in enumerate(out10) if c["cls"] == "near"]
    print(f"\nEP-day LOW band {B:.2f}: {len(nm10)} near-misses at 10d")
    for k, n, c in nm10:
        P = n["ep"]["l"]
        t20 = next((j for j, d in enumerate(n["fwd"][:20]) if d["l"] <= P), None)
        t60 = next((j for j, d in enumerate(n["fwd"]) if d["l"] <= P), None)
        status = (f"touches day {t20+1} (within 20d)" if t20 is not None else
                  (f"touches day {t60+1} (beyond 20d)" if t60 is not None else
                   "NEVER touches in 60d"))
        print(f"   {n['nm']:<22} dist {c['dist']:.2f}xADR -> {status}"
              f"   exc from approach {c['exc_appr']:+6.1f}xADR")

print("\n" + "=" * 100)
print("5b) DOES THE LADDER CATCH THE LOW-PIVOT NEAR-MISSES ANYWAY? (20d, band 0.50) — "
      "and what the proximity entry is worth vs the deepest TOUCHED pivot")
print("=" * 100)
out = results[("EP-day LOW", 20, 0.5)]
for k, (n, c) in enumerate(out):
    if c["cls"] != "near":
        continue
    caught = None
    for pname in ("EP-day CLOSE", "EP-day HIGH"):
        cc = results[(pname, 20, 0.5)][k][1]
        if cc["cls"] == "touched":
            pv = n["ep"]["c"] if pname == "EP-day CLOSE" else n["ep"]["h"]
            caught = (pname, pv, cc)
            break
    if caught:
        pname, pv, cc = caught
        impr = (pv - c["appr"]) / (n["adr"] * c["appr"])
        print(f"   {n['nm']:<22} ladder fills at {pname} {pv:>8.2f} (day {cc['j']+1}); "
              f"proximity entry {c['appr']:>8.2f} is {impr:+.2f}xADR better priced "
              f"({100*(pv-c['appr'])/c['appr']:+.1f}%)")
    else:
        print(f"   {n['nm']:<22} NO pivot touched — fully forfeited without proximity")
