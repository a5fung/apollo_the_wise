"""#655 step 1 — IDENTITY TEST, TWO-KEY FORM (addendum to identity_test.py, written 2026-09-27 AFTER
identity_test.py's results were seen — so this file is labelled POST-HOC wherever it matters).

WHY AN ADDENDUM
  The pre-registered SEARCHED test (best of 19 exemplar baskets) failed its own sanity read:
  47 of 113 judgeable themes flagged at the declared 0.10 bar, including names that are plainly
  right (Canadian Big Banks, U.S. Domestic Passenger Airlines, Regulated Natural Gas Utilities),
  with gaps LARGER than the miners'. No bar separates them — the 3-name exemplar references carry
  style (beta / defensiveness / retail speculation), and a max over 19 references finds one by chance.

WHAT THIS FILE TESTS — the same bars, the alternative NAMED instead of searched
  KEY 1 (evidence names the alternative, never a search): the only $0 deterministic source on
      today's board is DUAL-HOMING — a member of theme T also sits in a live theme T' whose e_code
      differs from T's. Every such other e_code is a candidate alternative driver for T.
  KEY 2 (the tape confirms, per member): for every judgeable member m of T,
      diff(m) = a(m, alt reference) - a(m, named reference)   (T's members excluded from both refs)
      m is an IDENTITY MISFIT if diff >= 0.10 (the bar declared in identity_test.py) and
      sep(named ref, alt ref) < 0.6 (the declared power guard).
  THEME VERDICT: share of judgeable members that are misfits
      >= 0.5  -> IDENTITY MISMATCH (the theme is named for the wrong driver)
      0 < share < 0.5 -> SPLIT COHORT (some members have migrated: the #491 "theme change for the
                         stocks" case)
      0 -> CONSISTENT.
  References: variant A (taxonomy exemplars) and B (IBIT for crypto; NVDA/SMCI/VRT/CRWV for AI-infra),
  both as declared in identity_test.py. No new constants.

NULL — what the BROKEN version of Key 1 produces
  For each candidate theme, replace the dual-home alternative with a RANDOM other ecosystem
  (not the named one), 200 draws; if random alternatives flag about as often, Key 1 is doing no work.

TEXT LEG, BUG FIX (not tuning): identity_test.py matched stems as raw substrings (the engine's own
  fallback does this on theme NAMES), which on free text read WULF's "expected to generate" as the
  E-BIO stem "gene". Re-run with whole-word matching (optional plural s). Stem lists untouched.
  Cross-check only.

Read-only. $0. No LLM.
"""
from __future__ import annotations

import csv
import random
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np

import identity_test as it

BAR = it.IDENTITY_GAP_BAR
SEP = it.SEP_GUARD


def member_contrast(theme, named, alt, ex, eco, variant):
    refs = it.references(eco, variant, set(theme["tickers"]))
    rn, nn = it.ref_series(ex, refs[named])
    ra, na = it.ref_series(ex, refs[alt])
    if rn is None or ra is None:
        return None
    sep = it.corr(rn, ra)
    rows = []
    for m in theme["tickers"]:
        if m not in ex:
            continue
        an, aa = it.corr(ex[m], rn), it.corr(ex[m], ra)
        if an is None or aa is None:
            continue
        rows.append((m, an, aa, aa - an))
    if len(rows) < it.MIN_JUDGEABLE_MEMBERS:
        return None
    guarded = sep is not None and sep >= SEP
    misfits = [r for r in rows if r[3] >= BAR] if not guarded else []
    share = len(misfits) / len(rows)
    verdict = ("UNJUDGEABLE_COLLINEAR" if guarded else
               "MISMATCH" if share >= 0.5 else "SPLIT" if share > 0 else "CONSISTENT")
    return {"rows": rows, "sep": sep, "share": share, "verdict": verdict, "misfits": [r[0] for r in misfits],
            "ref_sizes": (nn, na)}


def main():
    eco = it.load_taxonomy()
    themes = it.load_themes()
    closes = it.load_closes()
    ex, sessions = it.excess_for(closes, it.RUN_DATE)
    out = []
    w = out.append
    w("#655 IDENTITY TEST — TWO-KEY FORM (POST-HOC addendum; bars unchanged from identity_test.py)")
    w(f"RUN_DATE={it.RUN_DATE} window={sessions[1]}..{sessions[-1]} BAR={BAR} SEP_GUARD={SEP}")

    # KEY 1 — dual-home candidates
    home = defaultdict(list)
    for th in themes:
        for m in th["tickers"]:
            home[m].append(th)
    cand = defaultdict(set)       # theme name -> {alt e_code}
    evidence = defaultdict(list)
    n_pairs = 0
    for th in themes:
        if th["e_code"] not in eco:
            continue
        for m in th["tickers"]:
            for other in home[m]:
                if other["name"] == th["name"] or other["e_code"] not in eco or other["e_code"] == th["e_code"]:
                    continue
                cand[th["name"]].add(other["e_code"])
                evidence[th["name"]].append((m, other["name"], other["e_code"]))
                n_pairs += 1
    judgeable_board = [th for th in themes if th["e_code"] in eco]
    multi = Counter(len(home[m]) for m in {m for th in themes for m in th["tickers"]})
    w(f"\n== KEY 1: dual-homing on the board ==")
    w(f"members by number of live themes holding them: {sorted(multi.items())}")
    w(f"(theme, member, other-ecosystem) evidence rows: {n_pairs}; themes with >=1 named alternative: "
      f"{len(cand)} of {len(judgeable_board)} mapped themes")

    rows_out = []
    for variant in ("A", "B"):
        w(f"\n== KEY 2, variant {variant} ==")
        verdicts = Counter()
        mis_members = 0
        judged_members = 0
        for th in themes:
            if th["name"] not in cand:
                continue
            best = None
            for alt in sorted(cand[th["name"]]):
                r = member_contrast(th, th["e_code"], alt, ex, eco, variant)
                if r is None:
                    rows_out.append([variant, th["name"], th["e_code"], alt, "", "", "", "UNJUDGEABLE", ""])
                    continue
                rows_out.append([variant, th["name"], th["e_code"], alt, len(r["rows"]), f"{r['share']:.2f}",
                                 f"{r['sep']:.2f}" if r["sep"] is not None else "", r["verdict"],
                                 ",".join(r["misfits"])])
                if best is None or r["share"] > best[1]["share"]:
                    best = (alt, r)
            if best is None:
                verdicts["UNJUDGEABLE"] += 1
                continue
            alt, r = best
            verdicts[r["verdict"]] += 1
            judged_members += len(r["rows"])
            mis_members += len(r["misfits"])
            ev = [e for e in evidence[th["name"]] if e[2] == alt]
            w(f"  {r['verdict']:<22} {th['name'][:58]:<58} {th['e_code']}->{alt} share {r['share']:.2f} "
              f"sep {None if r['sep'] is None else round(r['sep'],2)} n={len(r['rows'])} refs {r['ref_sizes']} "
              f"misfits {r['misfits']} | named by {[(e[0], e[1][:32]) for e in ev][:3]}")
        w(f"verdicts (best alternative per theme): {dict(verdicts)}; members judged {judged_members}, misfits {mis_members}")

        # NULL — random alternative instead of the named one
        rng = random.Random(655)
        codes = sorted(eco)
        rates, split_or_mis = [], []
        for _ in range(it.NULL_DRAWS):
            flagged = judged = anyflag = 0
            for th in themes:
                if th["name"] not in cand:
                    continue
                pool = [c for c in codes if c != th["e_code"]]
                alt = rng.choice(pool)
                r = member_contrast(th, th["e_code"], alt, ex, eco, variant)
                if r is None or r["verdict"] == "UNJUDGEABLE_COLLINEAR":
                    continue
                judged += 1
                flagged += r["verdict"] == "MISMATCH"
                anyflag += r["verdict"] in ("MISMATCH", "SPLIT")
            rates.append(flagged / max(judged, 1))
            split_or_mis.append(anyflag / max(judged, 1))
        jud = sum(v for k, v in verdicts.items() if k in ("MISMATCH", "SPLIT", "CONSISTENT"))
        real = verdicts["MISMATCH"] / max(jud, 1)
        real_any = (verdicts["MISMATCH"] + verdicts["SPLIT"]) / max(jud, 1)
        w(f"NULL (random alternative, {it.NULL_DRAWS} draws): MISMATCH rate median {statistics.median(rates):.2f} "
          f"(p95 {np.percentile(rates,95):.2f}); MISMATCH-or-SPLIT median {statistics.median(split_or_mis):.2f} "
          f"(p95 {np.percentile(split_or_mis,95):.2f}) | REAL mismatch {verdicts['MISMATCH']}/{jud} = {real:.2f}, "
          f"mismatch-or-split {verdicts['MISMATCH']+verdicts['SPLIT']}/{jud} = {real_any:.2f}")

    # The #491 theme under the NAMED contrast, both variants, member rows
    w("\n== #491: Bitcoin Mining Stocks Rotation Reversal, named E-CRYPTO vs E-AIINFRA (named by CIFR's dual-home) ==")
    th = next(t for t in themes if t["name"] == "Bitcoin Mining Stocks Rotation Reversal")
    for variant in ("A", "B"):
        r = member_contrast(th, "E-CRYPTO", "E-AIINFRA", ex, eco, variant)
        w(f"variant {variant}: verdict {r['verdict']} share {r['share']:.2f} sep {r['sep']:.2f} refs {r['ref_sizes']}")
        for m, an, aa, d in sorted(r["rows"], key=lambda x: -x[3]):
            w(f"   {m:<5} crypto {an:+.2f}  AI-infra {aa:+.2f}  diff {d:+.2f}  {'MISFIT' if d >= BAR else ''}")
        cn = statistics.median(x[1] for x in r["rows"])
        ca = statistics.median(x[2] for x in r["rows"])
        w(f"   theme median: crypto {cn:+.2f}  AI-infra {ca:+.2f}")

    # Homeless converts: which live theme would the tape put them in? (co-movement to each theme basket)
    w("\n== Homeless / mis-homed converts: best live-theme basket by the engine's own co-movement (0.35 bar) ==")
    baskets = it.mac.build_baskets(themes, ex, stages=("Nascent", "Accelerating", "Mainstream", "Fading"))
    for m in ["CORZ", "WULF", "APLD", "IREN", "HUT", "CIFR", "ABTC", "MARA"]:
        if m not in ex:
            continue
        sc = []
        for b in baskets:
            c, n, k = it.mac.correlate(ex[m], b, exclude=m)
            if c is not None:
                sc.append((c, b.name, b.stage))
        sc.sort(reverse=True)
        w(f"  {m:<5} " + " | ".join(f"{nm[:40]} [{st}] {c:.2f}" for c, nm, st in sc[:3]))

    # TEXT LEG — word-boundary fix
    w("\n== TEXT LEG (whole-word stems, cross-check) ==")
    alerts = defaultdict(list)
    with open(it.HERE / "alerts.psv") as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            if len(p) < 3:
                continue
            d = date.fromisoformat(p[1])
            if it.RUN_DATE - timedelta(days=90) <= d < it.RUN_DATE:
                alerts[p[0]].append((d, p[2]))
    pats = {c: [re.compile(r"\b" + re.escape(s) + r"s?\b") for s in e["stems"]] for c, e in eco.items()}

    def driver(txt):
        t = (txt or "").lower()
        hits = {c: sum(1 for p in ps if p.search(t)) for c, ps in pats.items()}
        top = max(hits.values())
        if top == 0:
            return None, hits
        tops = [c for c, v in hits.items() if v == top]
        return (tops[0] if len(tops) == 1 else None), {c: v for c, v in hits.items() if v}
    called = contra = 0
    for th in themes:
        if th["e_code"] not in eco:
            continue
        for m in th["tickers"]:
            if not alerts.get(m):
                continue
            d, txt = max(alerts[m])
            td, _ = driver(txt)
            if td is None:
                continue
            called += 1
            contra += td != th["e_code"]
    w(f"member latest-catalysts with a whole-word call: {called}; text driver != theme's named driver: {contra}")
    for m in it.COHORT_491:
        if alerts.get(m):
            d, txt = max(alerts[m])
            td, hits = driver(txt)
            w(f"  {m:<5} {d} text-driver={td} hits={hits}")
        else:
            w(f"  {m:<5} no alert in 90d")

    with open(it.HERE / "identity_twokey_per_theme.tsv", "w") as f:
        cw = csv.writer(f, delimiter="\t")
        cw.writerow(["variant", "theme", "named", "alt_named_by_dualhome", "n_judged", "misfit_share", "sep",
                     "verdict", "misfits"])
        cw.writerows(rows_out)
    (it.HERE / "identity_twokey_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
