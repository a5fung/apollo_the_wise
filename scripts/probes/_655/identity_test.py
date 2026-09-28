"""#655 step 1 — THE IDENTITY TEST: is a theme's NAMED driver what actually drives its members?

PRE-REGISTRATION — every rule, window, reference set and bar below was written 2026-09-27 BEFORE
the price pull (`closes.psv`) or the alert pull (`alerts.psv`) was run. The output file echoes these
constants in its header so no number can later be read against a different bar.

WHY THIS TEST EXISTS
  A co-movement test asks "do these stocks belong together?" and passes #491: IREN moves with the
  miners at 0.70-0.83. What is wrong there is the IDENTITY — the driver the theme is named for.
  "Bitcoin Mining Stocks Rotation Reversal" claims bitcoin; the operator says the group's driver is
  now AI compute. This test asks the question a co-movement test cannot: of the drivers the system
  already knows about, which one do the members actually move with — and is it the one named?

POPULATION
  Every non-Retired theme on the latest board (DISTINCT ON name, theme_date >= CURRENT_DATE-7),
  pulled once to live_themes_2026-09-27.psv. Named driver N(T) = the theme's stored e_code in
  mi_theme_ecosystems (Haiku reading of the theme NAME at birth; keyword fallback; $0 to read).
  E-UNASSIGNED / no mapping => unjudgeable, counted separately.

REFERENCE SERIES (two variants, BOTH declared now, BOTH reported — never pick after seeing results)
  A (primary) = the operator-signed taxonomy (theme_ecosystems.yaml, 2026-07-14): each ecosystem's
      `exemplars`, equal-weight, EXCLUDING EVERY MEMBER OF THE THEME UNDER TEST (a group cannot be
      its own reference). Basket size after exclusion is reported; size 1 = low-confidence read.
      An ecosystem with 0 exemplars left is unjudgeable for that theme.
  B (driver-asset) = A, except two references are replaced by the task's named driver series:
      E-CRYPTO  := {IBIT}            (the bitcoin asset itself, not miner equities)
      E-AIINFRA := {NVDA, SMCI, VRT, CRWV}
      (still excluding the theme's own members).

MATHS — the engine's own, imported, never re-derived
  agents/market_intelligence/market_adjusted_correlation.py: SPY-subtracted daily log returns,
  60 sessions STRICTLY before the run date, Pearson vs an equal-weight basket mean, >= 30
  overlapping sessions. Run date = 2026-09-26 (so the window ends on the 09-25 close, the last
  data in mi_daily_closes). Reference baskets are built with min_members=1 (a reference is a
  driver series, not a candidate group), and their size is reported.

MEMBER AFFINITY   a(m, E) = corr(excess(m), reference(E) minus T's members)
THEME VERDICT     judgeable members: >= 2 members with usable history.
  F_N  = median over members of a(m, N)
  E*   = the ecosystem E != N with the highest median a(m, E);  F_* its median
  gap  = F_* - F_N
  S    = share of judgeable members with a(m, E*) > a(m, N)
  sep  = corr(reference(N), reference(E*)) over the same window (POWER GUARD)
  MISMATCH  <=> gap >= IDENTITY_GAP_BAR AND S >= MAJORITY AND sep < SEP_GUARD
  UNJUDGEABLE(collinear) <=> gap >= bar AND S >= majority AND sep >= SEP_GUARD
  CONSISTENT otherwise.
  Declared bar 0.10; neighbours 0.05 / 0.15 reported for his tradeoff. MAJORITY 0.5. SEP_GUARD 0.6.

CONTROLS — declared before measuring, no fitting
  positive: themes whose e_code is visibly a keyword mis-map (Electronics Manufacturing Services ->
            E-HLTH; IT Consulting & BPO -> E-HLTH) SHOULD flag.
  negative: themes built from their own ecosystem's exemplars (Network Security & Zero-Trust Edge,
            Emerging Quantum Computing Rally) should NOT flag.
  null (what the BROKEN system would produce): shuffle the e_codes across judgeable themes,
            200 draws; the flag rate under a random mapping must be far above the real one or the
            test does not discriminate.
  AI family (E-AISEMI / E-AIINFRA / E-SAAS / E-CYBR — "AI is deliberately distributed") flags are
            reported separately as the expected noise band; not suppressed.

TIME LEG — identity lag (#491 instance)
  For the cohort {HUT, ABTC, CIFR, IOND, BTDR, CLSK, MARA, RIOT, IREN, CORZ, WULF, APLD}: roll the
  affinity per session. d(D) = cohort median of [a(m, AI-infra ref) - a(m, crypto ref)], window =
  60 sessions strictly before D, each variant's references (cohort excluded). Flip date = first D
  where d > 0 for >= 10 consecutive sessions. Lag = sessions from flip date to 2026-09-26 while the
  cohort's theme still carries E-CRYPTO.

CATALYST-TEXT LEG — cross-check only (the stems are known to collide: services/mining/power)
  mi_ep_alerts.catalyst for each member, 90 calendar days before the run date. Text driver = the
  ecosystem whose taxonomy keyword_stems match the most distinct stems in that catalyst; ties or
  zero hits => no call. Theme-level: share of members with a called catalyst whose text driver != N.

Read-only. $0. No LLM. No prod writes.
"""
from __future__ import annotations

import csv
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from agents.market_intelligence import market_adjusted_correlation as mac  # noqa: E402

HERE = Path(__file__).resolve().parent
RUN_DATE = date(2026, 9, 26)
IDENTITY_GAP_BAR = 0.10
NEIGHBOUR_BARS = (0.05, 0.15)
MAJORITY = 0.5
SEP_GUARD = 0.6
MIN_JUDGEABLE_MEMBERS = 2
NULL_DRAWS = 200
SUSTAIN_SESSIONS = 10
AI_FAMILY = {"E-AISEMI", "E-AIINFRA", "E-SAAS", "E-CYBR"}
COHORT_491 = ["HUT", "ABTC", "CIFR", "IOND", "BTDR", "CLSK", "MARA", "RIOT", "IREN", "CORZ", "WULF", "APLD"]
VARIANT_B_OVERRIDES = {"E-CRYPTO": ["IBIT"], "E-AIINFRA": ["NVDA", "SMCI", "VRT", "CRWV"]}
POS_CONTROLS = ["Electronics Manufacturing Services (EMS) Providers",
                "IT Consulting & Business Process Outsourcing Services"]
NEG_CONTROLS = ["Network Security & Zero-Trust Edge", "Emerging Quantum Computing Rally"]


def load_taxonomy():
    doc = yaml.safe_load((REPO / "theme_ecosystems.yaml").read_text())
    eco = {}
    for e in doc["ecosystems"]:
        if e["e_code"] == "E-UNASSIGNED":
            continue
        eco[e["e_code"]] = {"exemplars": [t.upper() for t in e.get("exemplars") or []],
                            "stems": [s.lower() for s in e.get("keyword_stems") or []]}
    return eco


def load_themes():
    rows = []
    with open(HERE / "live_themes_2026-09-27.psv") as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            rows.append({"name": p[0], "stage": p[1], "theme_date": p[2], "days_active": p[3],
                         "source": p[4], "tickers": [t for t in p[5].split(",") if t],
                         "e_code": p[6] or None, "method": p[7] or None, "assigned": p[8] or None,
                         "description": p[9] if len(p) > 9 else ""})
    return rows


def load_closes():
    closes = defaultdict(dict)
    with open(HERE / "closes.psv") as f:
        for line in f:
            t, d, c = line.rstrip("\n").split("|")[:3]
            if c:
                closes[t][date.fromisoformat(d)] = float(c)
    return closes


def excess_for(closes, before):
    sessions = mac.session_index(closes["SPY"], before)
    mret = mac.log_returns(closes["SPY"], sessions)
    ex = mac.excess_returns(closes, sessions, mret)
    return {t: v for t, v in ex.items() if mac.usable(v, mac.BELONGING_MIN_OVERLAP_SESSIONS)}, sessions


def ref_series(ex, tickers):
    rows = [ex[t] for t in tickers if t in ex]
    if not rows:
        return None, 0
    return mac._basket_mean(np.vstack(rows), 1), len(rows)


def corr(a, b):
    if a is None or b is None:
        return None
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < mac.BELONGING_MIN_OVERLAP_SESSIONS or a[m].std() < 1e-12 or b[m].std() < 1e-12:
        return None
    return float(np.corrcoef(a[m], b[m])[0, 1])


def references(eco, variant, exclude):
    out = {}
    for code, e in eco.items():
        ex_list = VARIANT_B_OVERRIDES[code] if (variant == "B" and code in VARIANT_B_OVERRIDES) else e["exemplars"]
        out[code] = [t for t in ex_list if t not in exclude]
    return out


def judge_theme(theme, named, ex, eco, variant, bar):
    members = [t for t in theme["tickers"] if t in ex]
    refs = references(eco, variant, set(theme["tickers"]))
    series = {c: ref_series(ex, tl) for c, tl in refs.items()}
    aff = {}
    for m in members:
        aff[m] = {c: corr(ex[m], s[0]) for c, s in series.items() if s[0] is not None}
    res = {"n_members": len(theme["tickers"]), "n_judgeable": len(members), "named": named,
           "ref_sizes": {c: s[1] for c, s in series.items()}}
    if named is None or named not in series or series[named][0] is None or len(members) < MIN_JUDGEABLE_MEMBERS:
        res["verdict"] = "UNJUDGEABLE"
        return res, aff
    med = {}
    for c in series:
        vals = [aff[m][c] for m in members if aff[m].get(c) is not None]
        if len(vals) >= MIN_JUDGEABLE_MEMBERS:
            med[c] = statistics.median(vals)
    if named not in med:
        res["verdict"] = "UNJUDGEABLE"
        return res, aff
    alts = {c: v for c, v in med.items() if c != named}
    best = max(alts, key=alts.get)
    gap = alts[best] - med[named]
    s = sum(1 for m in members if aff[m].get(best) is not None and aff[m].get(named) is not None
            and aff[m][best] > aff[m][named]) / len(members)
    sep = corr(series[named][0], series[best][0])
    if gap >= bar and s >= MAJORITY:
        verdict = "UNJUDGEABLE_COLLINEAR" if (sep is not None and sep >= SEP_GUARD) else "MISMATCH"
    else:
        verdict = "CONSISTENT"
    res.update({"F_named": med[named], "best_alt": best, "F_alt": alts[best], "gap": gap,
                "share_prefer_alt": s, "sep": sep, "verdict": verdict,
                "named_rank": 1 + sum(1 for v in med.values() if v > med[named]),
                "n_ecos": len(med)})
    return res, aff


def run_board(themes, ex, eco, variant, bar, codes=None):
    out = []
    for i, th in enumerate(themes):
        named = codes[i] if codes is not None else (th["e_code"] if th["e_code"] in eco else None)
        r, _ = judge_theme(th, named, ex, eco, variant, bar)
        out.append(r)
    return out


def stems_hit(text, stems):
    t = (text or "").lower()
    return sum(1 for s in stems if s in t)


def main():
    eco = load_taxonomy()
    themes = load_themes()
    closes = load_closes()
    ex, sessions = excess_for(closes, RUN_DATE)
    out = []
    w = out.append
    w("#655 IDENTITY TEST — declared constants (pre-registered before the pulls)")
    w(f"RUN_DATE={RUN_DATE} window={sessions[1]}..{sessions[-1]} ({len(sessions)-1} returns) "
      f"GAP_BAR={IDENTITY_GAP_BAR} neighbours={NEIGHBOUR_BARS} MAJORITY={MAJORITY} SEP_GUARD={SEP_GUARD} "
      f"MIN_JUDGEABLE={MIN_JUDGEABLE_MEMBERS} NULL_DRAWS={NULL_DRAWS} SUSTAIN={SUSTAIN_SESSIONS}")
    # ── population
    w("\n== POPULATION ==")
    w(f"themes on board: {len(themes)}")
    w("stage: " + str(Counter(t['stage'] for t in themes)))
    w("source: " + str(Counter(t['source'] for t in themes)))
    w("e_code method: " + str(Counter(t['method'] for t in themes)))
    w("e_code: " + str(Counter(t['e_code'] for t in themes)))
    allm = {m for t in themes for m in t["tickers"]}
    w(f"distinct members: {len(allm)}; with usable 60-session history: {sum(1 for m in allm if m in ex)}")

    per_theme_rows = []
    for variant in ("A", "B"):
        w(f"\n== VARIANT {variant} ==")
        res = run_board(themes, ex, eco, variant, IDENTITY_GAP_BAR)
        judg = [r for r in res if r["verdict"] != "UNJUDGEABLE"]
        w(f"judgeable themes: {len(judg)} of {len(res)}")
        for bar in (NEIGHBOUR_BARS[0], IDENTITY_GAP_BAR, NEIGHBOUR_BARS[1]):
            rb = run_board(themes, ex, eco, variant, bar)
            vc = Counter(r["verdict"] for r in rb)
            mis = [(themes[i]["name"], r) for i, r in enumerate(rb) if r["verdict"] == "MISMATCH"]
            ai_only = sum(1 for _, r in mis if r["named"] in AI_FAMILY and r["best_alt"] in AI_FAMILY)
            w(f"bar {bar:.2f}: {dict(vc)} | mismatches in AI family (noise band): {ai_only} | outside: {len(mis)-ai_only}")
        # named rank distribution
        ranks = Counter(r.get("named_rank") for r in judg)
        w("named ecosystem's rank among references (1 = members move most with the named driver): "
          + str(sorted(ranks.items())))
        # the mismatches at declared bar
        w(f"-- MISMATCH list at bar {IDENTITY_GAP_BAR} --")
        conf = Counter()
        for i, r in enumerate(res):
            th = themes[i]
            per_theme_rows.append([variant, th["name"], th["stage"], th["source"], th["method"], r["named"],
                                   r.get("best_alt"), r["n_members"], r["n_judgeable"],
                                   f"{r.get('F_named', float('nan')):.3f}", f"{r.get('F_alt', float('nan')):.3f}",
                                   f"{r.get('gap', float('nan')):.3f}", f"{r.get('share_prefer_alt', float('nan')):.2f}",
                                   f"{(r.get('sep') if r.get('sep') is not None else float('nan')):.3f}",
                                   r.get("named_rank"), r["verdict"],
                                   r["ref_sizes"].get(r["named"]) if r["named"] else None,
                                   r["ref_sizes"].get(r.get("best_alt")) if r.get("best_alt") else None])
            if r["verdict"] in ("MISMATCH", "UNJUDGEABLE_COLLINEAR"):
                conf[(r["named"], r["best_alt"])] += 1
                w(f"  {r['verdict']:<22} {th['name'][:62]:<62} [{th['stage']},{th['method']}] "
                  f"named {r['named']} {r['F_named']:.2f} -> {r['best_alt']} {r['F_alt']:.2f} "
                  f"gap {r['gap']:.2f} share {r['share_prefer_alt']:.2f} sep {r['sep'] if r['sep'] is None else round(r['sep'],2)} "
                  f"n={r['n_judgeable']} refsz {r['ref_sizes'].get(r['named'])}/{r['ref_sizes'].get(r['best_alt'])}")
        w("confusion (named -> best alt): " + str(conf.most_common()))
        mm = [r for r in res if r["verdict"] == "MISMATCH"]
        w("mismatches by mapping method: " + str(Counter(themes[i]["method"] for i, r in enumerate(res) if r["verdict"] == "MISMATCH")))
        # controls
        w("-- controls --")
        for nm in POS_CONTROLS + NEG_CONTROLS + ["Bitcoin Mining Stocks Rotation Reversal", "AI data-center power buildout",
                                                   "Cloud Data Storage & Analytics Infrastructure",
                                                   "Emerging AI Compute & Cloud Infrastructure Platforms"]:
            i = next((k for k, t in enumerate(themes) if t["name"] == nm), None)
            if i is None:
                w(f"  {nm}: NOT ON BOARD")
                continue
            r = res[i]
            tag = "POS" if nm in POS_CONTROLS else ("NEG" if nm in NEG_CONTROLS else "491")
            if r["verdict"] == "UNJUDGEABLE":
                w(f"  [{tag}] {nm}: UNJUDGEABLE (judgeable members {r['n_judgeable']})")
            else:
                w(f"  [{tag}] {nm}: {r['verdict']} named {r['named']} F={r['F_named']:.2f} rank {r['named_rank']}/{r['n_ecos']} "
                  f"best alt {r['best_alt']} {r['F_alt']:.2f} gap {r['gap']:.2f} share {r['share_prefer_alt']:.2f} "
                  f"sep {None if r['sep'] is None else round(r['sep'],2)}")
        # null — shuffled mapping
        judg_idx = [i for i, r in enumerate(res) if r["verdict"] != "UNJUDGEABLE"]
        codes_real = [themes[i]["e_code"] for i in judg_idx]
        rng = random.Random(655)
        rates = []
        for _ in range(NULL_DRAWS):
            sh = codes_real[:]
            rng.shuffle(sh)
            codes = [None] * len(themes)
            for k, i in enumerate(judg_idx):
                codes[i] = sh[k]
            rb = run_board(themes, ex, eco, variant, IDENTITY_GAP_BAR, codes=codes)
            flagged = sum(1 for i in judg_idx if rb[i]["verdict"] == "MISMATCH")
            judged = sum(1 for i in judg_idx if rb[i]["verdict"] != "UNJUDGEABLE")
            rates.append(flagged / max(judged, 1))
        real_rate = len(mm) / max(len(judg), 1)
        w(f"NULL (e_codes shuffled across {len(judg_idx)} judgeable themes, {NULL_DRAWS} draws): "
          f"mismatch rate median {statistics.median(rates):.2f} (p5 {np.percentile(rates,5):.2f}, p95 {np.percentile(rates,95):.2f}) "
          f"vs REAL {len(mm)}/{len(judg)} = {real_rate:.2f}")

    with open(HERE / "identity_per_theme.tsv", "w") as f:
        cw = csv.writer(f, delimiter="\t")
        cw.writerow(["variant", "theme", "stage", "source", "method", "named", "best_alt", "n_members", "n_judgeable",
                     "F_named", "F_alt", "gap", "share_prefer_alt", "sep", "named_rank", "verdict",
                     "named_ref_size", "alt_ref_size"])
        cw.writerows(per_theme_rows)

    # ── member-level for the #491 cohort, today
    w("\n== #491 COHORT — member-level affinity today (cohort excluded from every reference) ==")
    cohort_set = set(COHORT_491)
    mem_rows = []
    for variant in ("A", "B"):
        refs = references(eco, variant, cohort_set)
        series = {c: ref_series(ex, tl) for c, tl in refs.items()}
        w(f"variant {variant}: crypto ref = {refs['E-CRYPTO']}, AI-infra ref = {refs['E-AIINFRA']}; "
          f"sep(crypto, AI-infra) = {corr(series['E-CRYPTO'][0], series['E-AIINFRA'][0])}")
        for m in COHORT_491:
            if m not in ex:
                w(f"  {m}: no usable history")
                continue
            a = {c: corr(ex[m], s[0]) for c, s in series.items() if s[0] is not None}
            top = sorted(((v, c) for c, v in a.items() if v is not None), reverse=True)[:3]
            homes = [t["name"] for t in themes if m in t["tickers"]]
            w(f"  {m:<5} crypto {a['E-CRYPTO']:+.2f}  AI-infra {a['E-AIINFRA']:+.2f}  diff {a['E-AIINFRA']-a['E-CRYPTO']:+.2f}  "
              f"top3 {[(c, round(v,2)) for v, c in top]}  themes {homes}")
            mem_rows.append([variant, m, f"{a['E-CRYPTO']:.3f}", f"{a['E-AIINFRA']:.3f}", "; ".join(homes)])
    with open(HERE / "identity_491_members.tsv", "w") as f:
        cw = csv.writer(f, delimiter="\t")
        cw.writerow(["variant", "ticker", "a_crypto", "a_aiinfra", "themes"])
        cw.writerows(mem_rows)

    # ── time leg
    w("\n== TIME LEG — rolling cohort median [a(AI-infra) - a(crypto)] ==")
    all_dates = sorted(d for d in closes["SPY"] if d <= date(2026, 9, 25))
    roll_rows = []
    for variant in ("A", "B"):
        refs = references(eco, variant, cohort_set)
        series_d = []
        for D in all_dates[61:] + [RUN_DATE]:
            exd, _ = excess_for(closes, D)
            cr, _ = ref_series(exd, refs["E-CRYPTO"])
            ai, _ = ref_series(exd, refs["E-AIINFRA"])
            diffs, cs, ais = [], [], []
            for m in COHORT_491:
                if m in exd:
                    c1, c2 = corr(exd[m], cr), corr(exd[m], ai)
                    if c1 is not None and c2 is not None:
                        diffs.append(c2 - c1); cs.append(c1); ais.append(c2)
            if len(diffs) >= 3:
                series_d.append((D, statistics.median(diffs), statistics.median(cs), statistics.median(ais), len(diffs)))
                roll_rows.append([variant, D.isoformat(), f"{statistics.median(diffs):.3f}",
                                  f"{statistics.median(cs):.3f}", f"{statistics.median(ais):.3f}", len(diffs)])
        flip = None
        run = 0
        for k, (D, d, *_r) in enumerate(series_d):
            run = run + 1 if d > 0 else 0
            if run >= SUSTAIN_SESSIONS and flip is None:
                flip = series_d[k - SUSTAIN_SESSIONS + 1][0]
        # last sustained flip that is still holding at the end
        cur = None
        run = 0
        for k, (D, d, *_r) in enumerate(series_d):
            if d > 0:
                run += 1
                if run == SUSTAIN_SESSIONS:
                    cur = series_d[k - SUSTAIN_SESSIONS + 1][0]
            else:
                run = 0
                cur = None
        w(f"variant {variant}: first window end {series_d[0][0]} .. {series_d[-1][0]}; first sustained flip {flip}; "
          f"current sustained regime began {cur}")
        for D, d, c, a, n in series_d[::10] + [series_d[-1]]:
            w(f"   {D}  median diff {d:+.2f}  crypto {c:+.2f}  AI {a:+.2f}  n={n}")
        if cur:
            lag = sum(1 for D, *_r in series_d if D > cur)
            w(f"   sessions from current-regime start {cur} to {series_d[-1][0]}: {lag}")
    with open(HERE / "identity_491_rolling.tsv", "w") as f:
        cw = csv.writer(f, delimiter="\t")
        cw.writerow(["variant", "run_date", "median_diff_ai_minus_crypto", "median_a_crypto", "median_a_ai", "n"])
        cw.writerows(roll_rows)

    # ── catalyst-text leg
    w("\n== CATALYST-TEXT LEG (cross-check; taxonomy keyword_stems on mi_ep_alerts.catalyst, 90d) ==")
    alerts = defaultdict(list)
    ap = HERE / "alerts.psv"
    if ap.exists():
        with open(ap) as f:
            for line in f:
                p = line.rstrip("\n").split("|")
                if len(p) < 3:
                    continue
                d = date.fromisoformat(p[1])
                if RUN_DATE - timedelta(days=90) <= d < RUN_DATE:
                    alerts[p[0]].append((d, p[2]))
    def text_driver(txt):
        hits = {c: stems_hit(txt, e["stems"]) for c, e in eco.items()}
        best = max(hits.values())
        if best == 0:
            return None
        tops = [c for c, v in hits.items() if v == best]
        return tops[0] if len(tops) == 1 else None
    n_called = n_contra = n_themes_any = 0
    contra_rows = []
    for th in themes:
        if th["e_code"] not in eco:
            continue
        called = contra = 0
        for m in th["tickers"]:
            if not alerts.get(m):
                continue
            d, txt = max(alerts[m])
            td = text_driver(txt)
            if td is None:
                continue
            called += 1
            if td != th["e_code"]:
                contra += 1
                contra_rows.append((th["name"], m, d, th["e_code"], td, txt[:110]))
        if called:
            n_themes_any += 1
        n_called += called
        n_contra += contra
    w(f"member-catalysts with a text call: {n_called} across {n_themes_any} themes; text driver != named: {n_contra}")
    for r in contra_rows:
        if r[0] in ("Bitcoin Mining Stocks Rotation Reversal", "AI data-center power buildout") or r[1] in COHORT_491:
            w(f"  {r}")
    w("cohort catalysts (latest in 90d, any theme or none):")
    for m in COHORT_491:
        if alerts.get(m):
            d, txt = max(alerts[m])
            w(f"  {m} {d} text-driver={text_driver(txt)} :: {txt[:150]}")
        else:
            w(f"  {m}: no alert in 90d")

    (HERE / "identity_test_out.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
