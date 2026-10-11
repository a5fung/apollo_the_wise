"""#146 detection page (2026-10-11) — turn the replay captures into the page's numbers. $0, reads captured files only.

Inputs (all in this directory): arm_rows.tsv.gz + triggered_reads.tsv (replay_146.py), q3_stored_rows.out (prod's stored
WATCH-or-better rows since 06-29, validity), q4_scores.tsv.gz + q5_score_days.out (the RS half of get_flag_universe,
2025-12-26 →, the 2026 board-membership tag), q1_candidates.out (population).
Run from the repo root:  python scripts/probes/_146_page/report_146.py > scripts/probes/_146_page/report_146.out
"""
from __future__ import annotations

import collections
import gzip
import os
import statistics as st
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = ("A", "B", "C", "D")
ARM_NAME = {"A": "A shipped (COILED prerequisite)", "B": "B D2 from STORED TIGHTENING+ (held labels count)",
            "C": "C D2 from RAW TIGHTENING+ (held labels do not count)", "D": "D no licence at all (from WATCH too)"}
ACTIONABLE = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")
WINDOW_START = date(2025, 1, 2)
SCOPE_START, SCOPE_END = date(2026, 7, 17), date(2026, 10, 9)     # the htf_scope doc's 60-scan-day window
VALID_FROM = date(2026, 9, 8)                                      # #592 anchor fix live in prod
Y26 = date(2026, 1, 2)
FWD = 10


def f(x):
    return None if x in ("", None) else float(x)


def read_tsv(path, gz=False):
    op = gzip.open if gz else open
    with op(path, "rt") as fh:
        hdr = None
        for ln in fh:
            p = ln.rstrip("\n").split("\t")
            if hdr is None:
                hdr = p
                continue
            if len(p) != len(hdr) or p[0].startswith("("):
                continue
            yield dict(zip(hdr, p))


def d(s):
    return date.fromisoformat(s)


# ───────────────────────────── load ─────────────────────────────
trig = list(read_tsv(os.path.join(HERE, "triggered_reads.tsv")))
for r in trig:
    r["sd"] = d(r["scan_date"])
    r["fwd"] = [float(x) for x in r["fwd_closes"].split(";")] if r["fwd_closes"] else []
    for k in ("base_high", "base_low", "base_high_close", "breakout_close", "breakout_volume_ratio", "pivot_high_price",
              "runup_pct", "range_ratio", "vol_ratio", "close", "dv20", "mom25"):
        r[k] = f(r[k])
rows = list(read_tsv(os.path.join(HERE, "arm_rows.tsv.gz"), gz=True))
for r in rows:
    r["sd"] = d(r["scan_date"])
stored = list(read_tsv(os.path.join(HERE, "q3_stored_rows.out")))
for r in stored:
    r["sd"] = d(r["scan_date"])
    r["raw"] = r["held_from_stage"] or r["stage"]
cand = list(read_tsv(os.path.join(HERE, "q1_candidates.out")))

scores = collections.defaultdict(dict)   # ticker -> score_date -> (rs_rank, rs_1m)
for r in read_tsv(os.path.join(HERE, "q4_scores.tsv.gz"), gz=True):
    scores[r["ticker"]][d(r["score_date"])] = (int(r["rs_rank"]) if r["rs_rank"] else None,
                                                f(r["rs_1m"]))
score_days = []                          # (date, n)
for r in read_tsv(os.path.join(HERE, "q5_score_days.out")):
    score_days.append((d(r["score_date"]), int(r["n"])))
score_days.sort()


def latest_complete_score_date(day):
    """db.latest_complete_score_date_sql: the latest score_date <= day whose row count is >= half the median
    count of the 10 most recent score_dates <= day."""
    upto = [(sd, n) for sd, n in score_days if sd <= day]
    if not upto:
        return None
    med = st.median([n for _, n in upto[-10:]])
    for sd, n in reversed(upto):
        if n >= 0.5 * med:
            return sd
    return None


def organic(r):
    """get_flag_universe paths (a)+(b) on the read day: a score row with rs_1m on the latest complete score date AND
    (rs_rank <= 200 OR rs_1m >= 80 OR close >= 1.25 x the 10-session min close) AND close >= $5 AND 20d $vol >= $5M.
    None when no score date exists (2025)."""
    sd = latest_complete_score_date(r["sd"])
    if sd is None or sd < date(2025, 12, 26):
        return None
    srow = scores.get(r["ticker"], {}).get(sd)
    if not srow or srow[1] is None:
        return False
    rs_rank, rs_1m = srow
    rs_ok = (rs_rank is not None and rs_rank <= 200) or rs_1m >= 80 or (r["mom25"] is not None and r["mom25"] >= 0.25)
    return bool(rs_ok and r["close"] >= 5.0 and r["dv20"] >= 5_000_000)


def rs_leader_recent(r, days=37):
    """RS-only half on ANY score date in the prior ~25 sessions (37 calendar days): rs_rank <= 200 or rs_1m >= 80.
    An approximation of 'the board would have admitted it during the flag' (the carry then keeps it)."""
    if r["sd"] < date(2025, 12, 26):
        return None
    lo = r["sd"] - timedelta(days=days)
    for sd, (rk, r1) in scores.get(r["ticker"], {}).items():
        if lo <= sd <= r["sd"] and ((rk is not None and rk <= 200) or (r1 is not None and r1 >= 80)):
            return True
    return False


# ───────────────────────────── A. population ─────────────────────────────
print("=" * 90)
print("A. POPULATION AND WINDOW")
tickers_cand = {r["ticker"] for r in cand}
print(f"  q1 candidates: {len(tickers_cand)} tickers (pole superset; leak_check.out: 0 stored WATCH+ tickers lost)")
days_all = sorted({r["sd"] for r in rows})
print(f"  replay scan days in window: {len(days_all)} ({days_all[0]} .. {days_all[-1]}); "
      f"scope-doc sub-window {SCOPE_START}..{SCOPE_END}: {sum(1 for x in days_all if SCOPE_START <= x <= SCOPE_END)} days; "
      f"2026 sub-window from {Y26}: {sum(1 for x in days_all if x >= Y26)} days")
by_arm_stage = {a: collections.Counter() for a in ARMS}
tick_by_arm_stage = {a: collections.defaultdict(set) for a in ARMS}
per_day = {a: collections.defaultdict(collections.Counter) for a in ARMS}
for r in rows:
    by_arm_stage[r["arm"]][r["stage"]] += 1
    tick_by_arm_stage[r["arm"]][r["stage"]].add(r["ticker"])
    per_day[r["arm"]][r["sd"]][r["stage"]] += 1
for a in ARMS:
    c = by_arm_stage[a]
    print(f"  arm {a}: rows WATCH {c['WATCH']} TIGHTENING {c['TIGHTENING']} COILED {c['COILED']} TRIGGERED {c['TRIGGERED']} "
          f"INVALIDATED {c['INVALIDATED']} | distinct names WATCH {len(tick_by_arm_stage[a]['WATCH'])} "
          f"TIGHTENING {len(tick_by_arm_stage[a]['TIGHTENING'])} COILED {len(tick_by_arm_stage[a]['COILED'])} "
          f"TRIGGERED {len(tick_by_arm_stage[a]['TRIGGERED'])}")
print("  per-day medians, arm A (stage counts over the replay population — wider than the live RS board):")
for label, lo, hi in (("full window", WINDOW_START, days_all[-1]), ("scope sub-window", SCOPE_START, SCOPE_END)):
    ds = [x for x in days_all if lo <= x <= hi]
    med = {s: st.median([per_day["A"][x][s] for x in ds]) for s in ACTIONABLE}
    print(f"    {label:16} n={len(ds)} days: WATCH {med['WATCH']:.0f} TIGHTENING {med['TIGHTENING']:.0f} "
          f"COILED {med['COILED']:.0f} TRIGGERED {med['TRIGGERED']:.0f}")

# ───────────────────────────── B. validity vs prod ─────────────────────────────
print("=" * 90)
print(f"B. VALIDITY — arm A raw read vs prod's stored raw read, ticker-days both have, scan_date >= {VALID_FROM}")
A_rows = {(r["ticker"], r["sd"]): r for r in rows if r["arm"] == "A"}
n = ok = 0
mism = collections.Counter()
mism_rows = []
mna = 0
stored_keep = [r for r in stored if r["sd"] >= VALID_FROM]
for r in stored_keep:
    if r["reason"].startswith("mna_filter:"):
        mna += 1
        continue
    if r["raw"] not in ACTIONABLE + ("INVALIDATED",):
        continue
    n += 1
    a = A_rows.get((r["ticker"], r["sd"]))
    rep = a["raw"] if a else "not kept (unqualified / no row)"
    if a and a["raw"] == r["raw"]:
        ok += 1
    else:
        mism[(r["raw"], rep)] += 1
        mism_rows.append((r["ticker"], r["scan_date"], r["raw"], rep, r["reason"][:50], (a or {}).get("reason", "")[:50]))
print(f"  stored rows compared: {n}; raw read reproduced: {ok} ({100*ok/max(n,1):.1f}%); mna_filter rows excluded: {mna}")
for k, v in mism.most_common():
    print(f"    stored {k[0]:11} -> replay {k[1]:40} {v}")
for m in mism_rows[:25]:
    print("    ", m)
# stored stage (with the hold) vs replay stage: the hold rule differs (prod re-armed holds until 10-11), so only informational
n2 = ok2 = 0
for r in stored_keep:
    if r["reason"].startswith("mna_filter:") or r["stage"] not in ACTIONABLE + ("INVALIDATED",):
        continue
    n2 += 1
    a = A_rows.get((r["ticker"], r["sd"]))
    ok2 += bool(a and a["stage"] == r["stage"])
print(f"  (stored STAGE incl. prod's re-arming hold vs replay stage with the one-night hold: {ok2} of {n2} — differs by design)")
# the real stored TRIGGERED reads since 06-29, do they appear in arm A?
A_trig = {(r["ticker"], r["sd"]) for r in trig if r["arm"] == "A"}
print("  stored REAL (un-held) TRIGGERED reads since 06-29 and whether arm A reproduces them:")
for r in stored:
    if r["stage"] == "TRIGGERED" and not r["held_from_stage"]:
        print(f"    {r['ticker']:6} {r['scan_date']}  in arm A: {(r['ticker'], r['sd']) in A_trig}  ({r['reason'][:60]})")
# replay WATCH+ rows on dates prod scanned but has no row for that ticker: universe difference (expected, not a mismatch)
stored_days = {r["sd"] for r in stored if r["sd"] >= VALID_FROM}
stored_keys = {(r["ticker"], r["sd"]) for r in stored}
extra = [r for r in rows if r["arm"] == "A" and r["sd"] in stored_days and r["stage"] in ACTIONABLE and (r["ticker"], r["sd"]) not in stored_keys]
print(f"  replay WATCH+ rows (arm A) on those scan dates with NO stored row in q3 for the ticker: {len(extra)} rows / "
      f"{len({r['ticker'] for r in extra})} names — q3 holds WATCH+/INVALIDATED/held/mna rows only, so these are EITHER not scanned "
      f"OR scanned and scored plain `unqualified` (a pivot divergence); settled by q6_no_row_check.sql on exactly these pairs:")
for r in sorted(extra, key=lambda r: (r["sd"], r["ticker"])):
    print(f"    {r['ticker']}\t{r['scan_date']}\treplay {r['stage']}\t{r['reason'][:50]}\tpivot {r['pivot_high_date']}")

# ───────────────────────────── C. TRIGGERED reads per arm ─────────────────────────────
print("=" * 90)
print("C. RAW TRIGGERED READS PER ARM (held_from_stage NULL), full window; flags = distinct (ticker, pivot date)")
reads = {a: {(r["ticker"], r["sd"]): r for r in trig if r["arm"] == a} for a in ARMS}
flags = {a: {(r["ticker"], r["pivot_high_date"]) for r in reads[a].values()} for a in ARMS}
for a in ARMS:
    sub26 = sum(1 for k in reads[a] if k[1] >= Y26)
    subsc = sum(1 for k in reads[a] if SCOPE_START <= k[1] <= SCOPE_END)
    print(f"  {ARM_NAME[a]:58} reads {len(reads[a]):4}  flags {len(flags[a]):4}  names {len({k[0] for k in reads[a]}):4} "
          f"| 2026-only reads {sub26:4} | scope sub-window reads {subsc}")
extras = {}
for a in ("B", "C", "D"):
    extras[a] = {k: v for k, v in reads[a].items() if k not in reads["A"]}
    lost = [k for k in reads["A"] if k not in reads[a]]
    print(f"  extras {a} minus A: {len(extras[a])} reads / {len({(v['ticker'], v['pivot_high_date']) for v in extras[a].values()})} flags / "
          f"{len({k[0] for k in extras[a]})} names;  A reads absent from {a}: {len(lost)} {lost[:6]}")
print(f"  nesting checks: A reads absent from B {len([k for k in reads['A'] if k not in reads['B']])}, "
      f"B reads absent from D {len([k for k in reads['B'] if k not in reads['D']])}, "
      f"C reads absent from B {len([k for k in reads['C'] if k not in reads['B']])}, "
      f"C reads absent from D {len([k for k in reads['C'] if k not in reads['D']])}  (0 everywhere = A ⊂ B ⊂ D and C ⊂ B)")
b_only = sorted(k for k in extras["B"] if k not in reads["C"])
c_only = sorted(k for k in extras["C"] if k not in reads["B"])
print(f"  STORED-vs-RAW split: in B not C (licensed only by a HELD label) {len(b_only)}: {[(t, s.isoformat()) for t, s in b_only]}")
print(f"                       in C not B {len(c_only)}: {[(t, s.isoformat()) for t, s in c_only]}")
for t, s in b_only:
    r = reads["B"][(t, s)]
    print(f"     {t} {s}: stored window {r['stored_window']} | raw window {r['raw_window']} | vol {r['breakout_volume_ratio']:.2f}x")
for t, s in c_only:
    r = reads["C"][(t, s)]
    print(f"     {t} {s}: stored window {r['stored_window']} | raw window {r['raw_window']} | vol {r['breakout_volume_ratio']:.2f}x")
TPLUS = ("TIGHTENING", "COILED", "TRIGGERED")


def yesterday_label(r):
    """The last entry of the stored window = yesterday's stored label (the reading htf.md's hand-off used)."""
    w = r["stored_window"].split(",") if r["stored_window"] else []
    return w[-1].rstrip("*") if w else None


for a in ("B", "C"):
    ex = list(extras[a].values())
    y_only = [r for r in ex if yesterday_label(r) in TPLUS]
    older = [r for r in ex if yesterday_label(r) not in TPLUS]
    print(f"  {a} extras by WHICH label licensed them: yesterday's stored label is TIGHTENING+ {len(y_only)}; "
          f"only an OLDER label in the 5-day window {len(older)}: {[(r['ticker'], r['scan_date'], r['stored_window']) for r in older]}")
d_from_watch = {k: v for k, v in extras["D"].items() if k not in reads["B"] and k not in reads["C"]}
print(f"  D minus (A|B|C) = breakouts from WATCH (no TIGHTENING-or-better label in the window, stored or raw): {len(d_from_watch)} reads")


# ───────────────────────────── D. forward read ─────────────────────────────
def forward(rs):
    out = collections.Counter()
    for r in rs:
        fw = r["fwd"]
        if len(fw) < FWD:
            out["censored"] += 1
            continue
        out["n"] += 1
        c10 = fw[FWD - 1]
        bh, bhc = r["base_high"], r["base_high_close"]
        out["held_bh"] += c10 >= bh
        out["fell_bh"] += c10 < bh
        if bhc is not None:
            out["held_bhc"] += c10 >= bhc
            out["fell_bhc"] += c10 < bhc
            out["never_under_bhc"] += all(c >= bhc for c in fw)
        out["never_under_bh"] += all(c >= bh for c in fw)
        out["c10_over_breakout_close"] += c10 > r["breakout_close"]
        out["ever_under_base_low"] += any(c < r["base_low"] for c in fw)
    return out


def fwd_line(label, rs):
    o = forward(rs)
    n_ = o["n"]
    if n_ == 0:
        print(f"  {label:50} n=0 settled, censored {o['censored']}")
        return
    print(f"  {label:50} n={n_:3} (censored {o['censored']:2}) | +10 close >= base_high: {o['held_bh']:3} ({100*o['held_bh']/n_:3.0f}%)  "
          f"fell back under: {o['fell_bh']:3} | never closed under base_high in 10: {o['never_under_bh']:3} ({100*o['never_under_bh']/n_:3.0f}%) | "
          f"vs base_high_CLOSE: held {o['held_bhc']:3} never-under {o['never_under_bhc']:3} | +10 close > breakout close: {o['c10_over_breakout_close']:3} | "
          f"closed under base_LOW within 10: {o['ever_under_base_low']:3}")


print("=" * 90)
print("D. FORWARD READ — detection quality (a chart fact at +10 sessions, not a trade): held above the level vs fell back")
sets = [
    ("A shipped reads", list(reads["A"].values())),
    ("B extras (D2 stored licence)", list(extras["B"].values())),
    ("C extras (D2 raw licence)", list(extras["C"].values())),
    ("B extras licensed ONLY by a held label", [reads["B"][k] for k in b_only]),
    ("D extras from WATCH (neither licence)", list(d_from_watch.values())),
    ("D all reads (every qualifying breakout)", list(reads["D"].values())),
]
for label, rs in sets:
    fwd_line(label, rs)
print("  — 2026-only sub-window (board membership taggable) —")
for label, rs in sets:
    fwd_line(label + " [2026]", [r for r in rs if r["sd"] >= Y26])
print("  — scope-doc sub-window 07-17 → 10-09 —")
for label, rs in sets:
    fwd_line(label + " [scope]", [r for r in rs if SCOPE_START <= r["sd"] <= SCOPE_END])

# ───────────────────────────── E. board membership tag (2026) ─────────────────────────────
print("=" * 90)
print("E. BOARD MEMBERSHIP TAG, 2026 reads only (mi_stock_scores starts 2025-12-26; 2025 reads cannot be tagged)")
for label, rs in sets[:5]:
    rs26 = [r for r in rs if r["sd"] >= Y26]
    org = [organic(r) for r in rs26]
    rec = [rs_leader_recent(r) for r in rs26]
    n_ = len(rs26)
    print(f"  {label:50} n={n_:3} | organic universe on the read day: {sum(1 for x in org if x):3} | "
          f"RS leader (rank<=200 or rs_1m>=80) on some day in the prior 25 sessions: {sum(1 for x in rec if x):3} | "
          f"price>=$5 & 20d $vol>=$5M on the day: {sum(1 for r in rs26 if r['close'] >= 5 and r['dv20'] >= 5e6):3}")
# forward read restricted to the taggable-and-in-universe subset
# The EXACT board test for the era q3 covers (2026-06-29 →): did prod store a WATCH-or-better / INVALIDATED row for the
# ticker on the read day? (q3 holds every such row for all tickers; a ticker prod did not scan, or scored `unqualified`,
# has none.) Exact where it applies; the RS tag above is the approximation for the rest of 2026.
Q3_FROM = date(2026, 6, 29)
stored_keys_all = {(r["ticker"], r["sd"]) for r in stored}
print(f"  EXACT board presence, reads since {Q3_FROM} (prod stored a WATCH+/INVALIDATED row for the ticker that day):")
for label, rs in sets[:5]:
    rs_q = [r for r in rs if r["sd"] >= Q3_FROM]
    on = [r for r in rs_q if (r["ticker"], r["sd"]) in stored_keys_all]
    off = [r for r in rs_q if (r["ticker"], r["sd"]) not in stored_keys_all]
    print(f"    {label:50} n={len(rs_q):3} | on the live board that day: {len(on):3} | not scanned / not stored: {len(off):3} "
          f"{[(r['ticker'], r['scan_date']) for r in off][:12]}")
    if label.startswith("B extras") and on:
        fwd_line("      B extras ON the live board that day [since 06-29]", on)
print("  forward read on the 2026 extras the board would plausibly have held (RS leader in the prior 25 sessions AND price/$vol gates):")
for label, rs in sets[1:3]:
    sub = [r for r in rs if r["sd"] >= Y26 and rs_leader_recent(r) and r["close"] >= 5 and r["dv20"] >= 5e6]
    fwd_line(label + " [2026, board-plausible]", sub)

# ───────────────────────────── F. the extras, listed ─────────────────────────────
print("=" * 90)
print("F. EVERY B EXTRA (D2 from stored TIGHTENING+), with its forward read.  cols: date ticker vol x | runup | base age | "
      "+10 close vs base_high (held/fell/cens) | never-under | stored window | raw window | organic(2026) | RS-leader-25")
for k in sorted(extras["B"], key=lambda k: (k[1], k[0])):
    r = reads["B"][k]
    fw = r["fwd"]
    if len(fw) >= FWD:
        verdict = "held" if fw[FWD - 1] >= r["base_high"] else "fell"
        never = "never-under" if all(c >= r["base_high"] for c in fw) else "dipped-under"
    else:
        verdict, never = f"cens({len(fw)})", "-"
    org = organic(r)
    rec = rs_leader_recent(r)
    print(f"  {r['scan_date']} {r['ticker']:6} {r['breakout_volume_ratio']:5.2f}x | runup {100*r['runup_pct']:4.0f}% | base {r['base_age']:>2} | "
          f"{verdict:8} {never:12} | S[{r['stored_window']}] R[{r['raw_window']}] | org {org} | rs25 {rec} | in C: {k in reads['C']}")

print("\n  APPENDIX BLOCK for the page — the B extras as 'TICKER mm-dd', by year (a flag that read twice is listed on each read):")
for yr in (2025, 2026):
    ks = sorted((k for k in extras["B"] if k[1].year == yr), key=lambda k: (k[1], k[0]))
    print(f"    {yr} ({len(ks)} reads, {len({k[0] for k in ks})} names): " + ", ".join(f"{t} {s.strftime('%m-%d')}" for t, s in ks))
print("  base age of the licensed vs unlicensed breakouts (the confound on the base_low column):")
for label, rs in (("A shipped", list(reads["A"].values())), ("B extras", list(extras["B"].values())), ("D from WATCH", list(d_from_watch.values()))):
    ages = sorted(int(r["base_age"]) for r in rs)
    print(f"    {label:12} n={len(ages):3} base age median {st.median(ages):.0f}  p25 {ages[len(ages)//4]}  p75 {ages[3*len(ages)//4]}  "
          f"share with base age <= 6: {100*sum(1 for a in ages if a <= 6)/len(ages):.0f}%")
# the base_low column with base age matched (>= 7 sessions) — does the WATCH gap survive?
for label, rs in (("A shipped", list(reads["A"].values())), ("B extras", list(extras["B"].values())), ("D from WATCH", list(d_from_watch.values()))):
    fwd_line(f"    {label} [base age >= 7]", [r for r in rs if int(r["base_age"]) >= 7])

# ───────────────────────────── G. CDNA ─────────────────────────────
print("=" * 90)
print("G. CDNA — the three breakouts the task names, per arm (replay rows; stored prod rows from q3 alongside)")
for day in ("2026-07-31", "2026-08-25", "2026-09-17"):
    print(f"  {day}:")
    for a in ARMS:
        rr = next((r for r in rows if r["arm"] == a and r["ticker"] == "CDNA" and r["scan_date"] == day), None)
        if rr:
            print(f"    arm {a}: stage {rr['stage']:10} raw {rr['raw']:10} {rr['reason'][:60]:60} S[{rr['stored_window']}] R[{rr['raw_window']}]")
    srow = next((r for r in stored if r["ticker"] == "CDNA" and r["scan_date"] == day), None)
    if srow:
        print(f"    prod  : stage {srow['stage']:10} held_from {srow['held_from_stage'] or '-':10} {srow['reason'][:60]}")
print("  CDNA chains 07-27 → 08-01 and 08-17 → 08-27, arm A replay vs prod stored (stage/held):")
for lo, hi in (("2026-07-27", "2026-08-01"), ("2026-08-17", "2026-08-27"), ("2026-09-11", "2026-09-18")):
    for r in sorted((r for r in rows if r["arm"] == "A" and r["ticker"] == "CDNA" and lo <= r["scan_date"] <= hi), key=lambda r: r["sd"]):
        srow = next((s for s in stored if s["ticker"] == "CDNA" and s["scan_date"] == r["scan_date"]), None)
        print(f"    {r['scan_date']} replay {r['stage']:10}/{r['held_from_stage'] or '-':10} {r['reason'][:42]:42} | "
              f"prod {(srow['stage'] if srow else 'no row'):10}/{(srow['held_from_stage'] or '-') if srow else '-':10} {(srow['reason'][:42] if srow else '')}")

# ───────────────────────────── H. scope-window overlap ─────────────────────────────
print("=" * 90)
print(f"H. OVERLAP WITH THE SCOPE DOC ({SCOPE_START} → {SCOPE_END}): the doc named CDNA 07-31, CDNA 08-25, EFOR 10-01 as "
      f"COILED-only breakouts; GSHD, HELP, QMCO passed both legs only after the base reset")
for a in ARMS:
    ks = sorted((k for k in reads[a] if SCOPE_START <= k[1] <= SCOPE_END), key=lambda k: (k[1], k[0]))
    print(f"  arm {a} reads in the sub-window ({len(ks)}): {[(t, s.isoformat()) for t, s in ks]}")

# ───────────────────────────── I. corpus cross-check ─────────────────────────────
print("=" * 90)
print("I. CORPUS CROSS-CHECK — what each arm said on each labelled date (stage / raw read / reason)")
CORPUS_DATES = [
    ("CDNA", "2026-08-18", "HTF positive (Soreide, bought 08-19; shared 08-25)"), ("CDNA", "2026-08-19", "same"),
    ("CDNA", "2026-08-25", "the first flag's breakout day"),
    ("CDNA", "2026-09-16", "second flag, day before the 09-17 break"), ("CDNA", "2026-09-17", "second flag's breakout (0.83x volume)"),
    ("CDNA", "2026-09-24", "Soreide follow-up label"),
    ("HNGE", "2026-08-21", "HTF positive (trader post 08-24)"), ("HNGE", "2026-08-24", "same"),
    ("MRNA", "2026-09-11", "HTF positive (Soreide 09-17, chart 09-16)"), ("MRNA", "2026-09-15", "same"),
    ("MRNA", "2026-09-16", "day before his breakout"), ("MRNA", "2026-09-17", "his breakout day"), ("MRNA", "2026-09-24", "PBA 'model book HTF'"),
    ("GH", "2026-06-24", "consolidation positive (06-27 review: 'flat basing… broke out the past few days')"),
    ("GH", "2026-06-25", "same"), ("GH", "2026-06-26", "same"),
    ("HNGE", "2026-06-24", "consolidation positive (06-27 review)"), ("HNGE", "2026-06-25", "same"), ("HNGE", "2026-06-26", "same"),
    ("HPE", "2026-06-02", "pointer ('a good candidate for HTF or delayed entry')"),
    ("NCI", "2026-06-26", "NEGATIVE ('NCI is not valid')"),
    ("ATAI", "2026-07-24", "NEGATIVE (buyout; M&A layer, not this function)"),
    ("OUST", "2026-06-29", "NEGATIVE (removal-list sign-off)"), ("SHAZ", "2026-06-29", "NEGATIVE"), ("SHAZ", "2026-06-30", "NEGATIVE"),
    ("REPL", "2026-08-10", "NEGATIVE"), ("REPL", "2026-08-11", "NEGATIVE"),
]
idx = {(r["arm"], r["ticker"], r["scan_date"]): r for r in rows if r["ticker"] in {c[0] for c in CORPUS_DATES}}
for t, day, note in CORPUS_DATES:
    parts = []
    for a in ARMS:
        r = idx.get((a, t, day))
        parts.append(f"{a}:{r['stage']}" + (f"(raw {r['raw']})" if r and r['raw'] != r['stage'] else "") if r else f"{a}:no row")
    r = idx.get(("A", t, day))
    print(f"  {t:5} {day}  {' '.join(parts):70} {(r['reason'][:55] if r else ''):55} — {note}")
print("  TRIGGERED reads for corpus tickers in the window, per arm:")
for t in ("CDNA", "HNGE", "MRNA", "GH", "HPE", "NCI", "ATAI", "OUST", "SHAZ", "REPL"):
    parts = []
    for a in ARMS:
        ks = sorted(k[1].isoformat() for k in reads[a] if k[0] == t)
        parts.append(f"{a}:{ks if ks else '-'}")
    print(f"    {t:5} {' | '.join(parts)}")

# ───────────────────────────── J. G8 side table ─────────────────────────────
print("=" * 90)
print("J. G8 SIDE TABLE — his read is 'ATR(14) falling' across the flag; ours is first-5 vs last-5 range/volume ratios.")
print("   ATR at the label date vs ATR at the pivot (pole top) and at the first base day; our ratios from the code's row, or "
      "recomputed with the code's own formula when the code rejected before that step ('rc').")
A_by = {(r["ticker"], r["scan_date"]): r for r in rows if r["arm"] == "A"}
A_days = collections.defaultdict(list)
for r in rows:
    if r["arm"] == "A":
        A_days[r["ticker"]].append(r["sd"])
for t in A_days:
    A_days[t].sort()
G8 = [("CDNA", "2026-08-19"), ("CDNA", "2026-08-25"), ("CDNA", "2026-09-17"), ("HNGE", "2026-08-24"), ("MRNA", "2026-09-16"),
      ("GH", "2026-06-25"), ("HNGE", "2026-06-25"), ("HPE", "2026-06-02")]
for t, day in G8:
    r = A_by.get((t, day))
    if not r:
        print(f"  {t} {day}: no row")
        continue
    pd_ = r["pivot_high_date"]
    atr_label = f(r["atr14_any"])
    atr_piv = f(A_by.get((t, pd_), {}).get("atr14_any")) if pd_ else None
    nxt = None
    if pd_:
        ds = A_days[t]
        i = ds.index(d(pd_)) if d(pd_) in ds else None
        if i is not None and i + 1 < len(ds):
            nxt = ds[i + 1]
    atr_b1 = f(A_by.get((t, nxt.isoformat()), {}).get("atr14_any")) if nxt else None
    rr = f(r["range_ratio"]) if r["range_ratio"] else f(r["rr_recomputed"])
    vr = f(r["vol_ratio"]) if r["vol_ratio"] else f(r["vr_recomputed"])
    tag = "" if r["range_ratio"] else " (rc)"
    print(f"  {t:5} {day} stage {r['stage']:11} raw {r['raw']:11} pivot {pd_} base_age {r['base_age']:>3} | "
          f"ATR14 label {atr_label if atr_label is None else round(atr_label, 3)} / at pivot {atr_piv if atr_piv is None else round(atr_piv, 3)} "
          f"-> {('%.2f' % (atr_label/atr_piv)) if atr_label and atr_piv else 'n/a'}x ; / first base day {atr_b1 if atr_b1 is None else round(atr_b1, 3)} "
          f"-> {('%.2f' % (atr_label/atr_b1)) if atr_label and atr_b1 else 'n/a'}x | range {rr if rr is None else round(rr, 2)} vol {vr if vr is None else round(vr, 2)}{tag} "
          f"| rmv5 {r['rmv_5d'] or '-'} rmv15 {r['rmv_15d'] or '-'} | fresh2bar {r['fresh_2bar_tr_pct'] or '-'} atr% {r['atr14_pct'] or '-'} | {r['reason'][:50]}")

# ───────────────────────────── K. volume-leg sensitivity (context) ─────────────────────────────
print("=" * 90)
print("K. CONTEXT — breakout volume of the arms' reads (the 1.5x leg is untouched in every arm; shows what the licence admits)")
for label, rs in sets[:3] + [sets[4]]:
    v = sorted(r["breakout_volume_ratio"] for r in rs if r["breakout_volume_ratio"] is not None)
    if v:
        print(f"  {label:50} n={len(v):3} vol x: median {st.median(v):.2f}  p25 {v[len(v)//4]:.2f}  p75 {v[3*len(v)//4]:.2f}  "
              f"runup median {100*st.median([r['runup_pct'] for r in rs]):.0f}%  base age median {st.median([int(r['base_age']) for r in rs]):.0f}")
