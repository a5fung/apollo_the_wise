"""#580 slice -- MEASURE the one-sided trim in constants.trimmed_mean.  READ-ONLY, $0, deterministic.

    python scripts/probes/_580/trimmed_mean_compare.py > scripts/probes/_580/trimmed_mean_compare_output.txt

Reads ONLY the JSONL files written once by trimmed_mean_capture.py (no DB access, no LLM). Nothing in the repo is
modified; production `trimmed_mean` is imported and used for arm A so A is the literal live code.

=====================================================================================================
PRE-REGISTRATION (written before the first result was produced; do not edit after seeing output)
=====================================================================================================
POPULATION   last 20 distinct mi_themes.theme_date values; rows with stage != 'Retired'.
             (The 21st-newest date is loaded only as "last night's roster" for the oldest date.)
ARMS         A = constants.trimmed_mean (drops lowest d, never the top; d=1 for n<=5, 2 for n<=10,
                 max(1,int(.2n)) above; n<3 -> plain mean)
             B = plain mean
             C = SYMMETRIC trim, the SAME d dropped from BOTH tails (literal reading of the ask).
                 Never degenerate (2d < n for all n>=3). Consequence stated up front: at n=3 and n=4 C
                 is the median (1 and 2 values kept); n<3 -> plain mean, so A=B=C there.

TWO SCORES THE TRIM FEEDS (read from code, not assumed):
  S1  ENGINE / DASHBOARD score = stored mi_themes.score.
        theme_engine.py:3792-3793,3833  momentum = trimmed_mean(rs_composite of STRONG members, rs>=50)
                                   momentum_score = min(momentum/100*50, 50)
        theme_engine.py:3834,3869,3976  momentum_score above; total_score = round(momentum_score + news_score, 1); rs_avg=round(momentum,1)
        news_score is NOT stored and is HELD FIXED:  news = stored_score - min(rs_avg/2, 50).
        For arm X:  S1_X = stored_score + 0.5*(m_X - m_A)   (m_* computed on the SAME member set, so any
        member-set reconstruction error cancels in the difference).
        Rows whose stored score has NO trim component are held FIXED in all arms (A=B=C):
          - Fading-branch rows  (rs_avg NULL; score = prev*0.8, theme_engine.py:3804-3817)
          - shadow_promoted rows (score = rs_avg = PLAIN untrimmed mean, no news; theme_engine.py:2420,2567)
          - rs_avg == 0 rows    (new theme with no member in stocks_by_ticker; theme_engine.py:6878-6879 -> 0)
        S1-all  = ranking of ALL non-Retired rows by S1 (the dashboard's population; fixed rows still occupy
                  ranks).  <-- PRIMARY (matches the task's stated population)
        S1-fed  = ranking of ONLY the rows whose score the trim actually feeds (fixed rows removed).
                  <-- sensitivity: the cleanest read of "what the trim does to rank order"
  S2  /theme score = briefing.py:681 comp = trimmed_mean(rs_composite of ALL stored members that have a
        same-date mi_stock_scores row -- NO rs>=50 filter), non-Fading only (briefing.py:_compute_scored_themes
        active = stage != 'Fading'). Whole score is the trim; nothing else to hold fixed.  <-- SECONDARY

MEMBER SET FOR S1 (reconstruct the engine's scoring-time set; stored tickers can differ because the
  engine adds/merges members AFTER scoring).  Cascade, first hit wins, hit = |A(set) - rs_avg| <= 0.051:
    iii  stored tickers with same-date rs_composite >= 50
    v    (last night's stored tickers  INTERSECT  tonight's stored tickers), rs >= 50
    vi   last night's stored tickers, rs >= 50
    iv   stored tickers, any rs (a brand-new theme is scored on ALL members, theme_engine.py:6878)
  No hit -> UNVERIFIED: use iii (or iv if iii empty). Reported, and a sensitivity excludes them.
  (Leader-pool replay is deliberately NOT attempted; the cascade already explains ~97%.)

METRICS per date, per score, per pair (A vs B) and (A vs C):
  Spearman rank correlation (average ranks for ties); top-10 overlap (ordinal rank, ties by name);
  number of themes whose ordinal rank moves by >= 3 places  (mover = |rank_A - rank_X| >= 3).
Biggest movers: the 10 largest |rank_A - rank_X| overall, with member counts.
Ordinal rank = position after sorting by (-score, name).

ADDENDUM (post-hoc, added AFTER the first output was read -- labelled EXTRA in the output, NOT part of the
pre-registered metric): section 7 (tie-robustness of the mover count), section 8 (day-over-day change of the
trim's own bias, as a proxy for stage-transition exposure) section 9 (S1 under the dashboard's default stage filter) and section 10 (scale-mismatched rows in the stored top-10). Also corrected line-number citations in this header.
=====================================================================================================
"""
import collections
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from agents.market_intelligence.constants import trimmed_mean  # noqa: E402  (arm A = live code)

HERE = pathlib.Path(__file__).parent


def _load(name):
    return [json.loads(ln) for ln in (HERE / name).read_text().splitlines() if ln.strip()]


# ---------------------------------------------------------------------------------------------
# arms
# ---------------------------------------------------------------------------------------------
def drop_count(n: int) -> int:
    """Mirror of the drop rule inside constants.trimmed_mean (asserted equal below)."""
    if n <= 5:
        return 1
    if n <= 10:
        return 2
    return max(1, int(n * 0.2))


def arm_A(v):
    return trimmed_mean(list(v)) if v else 0.0


def arm_B(v):
    return sum(v) / len(v) if v else 0.0


def arm_C(v):
    n = len(v)
    if n < 3:
        return arm_B(v)
    d = drop_count(n)
    kept = sorted(v)[d:n - d]
    return sum(kept) / len(kept)


def _selftest():
    import random
    rnd = random.Random(580)
    for n in list(range(0, 40)) * 5:
        v = [rnd.uniform(0, 100) for _ in range(n)]
        if n >= 3:
            exp = sum(sorted(v)[drop_count(n):]) / (n - drop_count(n))
        else:
            exp = (sum(v) / n) if n else 0.0
        assert abs(arm_A(v) - exp) < 1e-9, (n, arm_A(v), exp)
        if n >= 3:
            assert 2 * drop_count(n) < n
    assert arm_C([1, 2, 3]) == 2 and arm_C([1, 2, 3, 100]) == 2.5


# ---------------------------------------------------------------------------------------------
# ranking helpers
# ---------------------------------------------------------------------------------------------
def ordinal_rank(items):
    """items: list of (key, score). -> {key: 1-based ordinal rank}, ties broken by key (name)."""
    order = sorted(items, key=lambda kv: (-kv[1], kv[0]))
    return {k: i + 1 for i, (k, _) in enumerate(order)}


def avg_rank(items):
    """average ranks (1 = highest score) for Spearman."""
    order = sorted(items, key=lambda kv: -kv[1])
    out, i = {}, 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and order[j + 1][1] == order[i][1]:
            j += 1
        r = (i + 1 + j + 1) / 2
        for k in range(i, j + 1):
            out[order[k][0]] = r
        i = j + 1
    return out


def spearman(a_items, x_items):
    ra, rx = avg_rank(a_items), avg_rank(x_items)
    keys = list(ra)
    n = len(keys)
    if n < 3:
        return float("nan")
    ma = sum(ra[k] for k in keys) / n
    mx = sum(rx[k] for k in keys) / n
    num = sum((ra[k] - ma) * (rx[k] - mx) for k in keys)
    da = sum((ra[k] - ma) ** 2 for k in keys) ** 0.5
    dx = sum((rx[k] - mx) ** 2 for k in keys) ** 0.5
    return num / (da * dx) if da and dx else float("nan")


def compare_arms(rows, key_a, key_x):
    """rows: list of dict with 'name', key_a, key_x. -> metrics dict + per-name ranks."""
    a_items = [(r["name"], r[key_a]) for r in rows]
    x_items = [(r["name"], r[key_x]) for r in rows]
    oa, ox = ordinal_rank(a_items), ordinal_rank(x_items)
    top_a = {k for k, v in oa.items() if v <= 10}
    top_x = {k for k, v in ox.items() if v <= 10}
    moves = {k: abs(oa[k] - ox[k]) for k in oa}
    return {
        "n": len(rows),
        "spearman": spearman(a_items, x_items),
        "top10": len(top_a & top_x),
        "movers3": sum(1 for m in moves.values() if m >= 3),
        "oa": oa, "ox": ox, "moves": moves,
    }


# ---------------------------------------------------------------------------------------------
# load + classify
# ---------------------------------------------------------------------------------------------
def main():
    _selftest()
    themes_all = _load("trimmed_mean_raw_themes.jsonl")
    scores = _load("trimmed_mean_raw_scores.jsonl")
    counts = _load("trimmed_mean_raw_score_counts.jsonl")

    all_dates = sorted({t["theme_date"] for t in themes_all})
    assert len(all_dates) == 21, len(all_dates)
    prev_of = {d: (all_dates[i - 1] if i else None) for i, d in enumerate(all_dates)}
    dates = all_dates[1:]                       # the 20 population dates
    assert len(dates) == 20

    rs = collections.defaultdict(dict)          # date -> ticker -> rs_composite (non-null only)
    for s in scores:
        if s["rs_composite"] is not None:
            rs[s["score_date"]][s["ticker"]] = float(s["rs_composite"])
    row_of = {(t["theme_date"], t["name"]): t for t in themes_all}

    # ---- _resolve_score_date check (db.py:8905): is each theme date a COMPLETE score run? ----
    cnt = {c["score_date"]: c["n"] for c in counts}
    recent = sorted(cnt.values(), reverse=True)  # not used for the bar; see below
    print("=" * 100)
    print("0. DATA-DATE CHECK (get_rs_for_tickers -> _resolve_score_date keeps the requested date only if the run is complete)")
    ns = [cnt[d] for d in dates if d in cnt]
    med = statistics.median(ns)
    bad = [d for d in dates if cnt.get(d, 0) < 0.5 * med]
    print(f"   score-run row counts on the 20 theme dates: min={min(ns)} median={med} max={max(ns)}; "
          f"dates below half the median (would fall back): {bad or 'none'}")
    missing_dates = [d for d in dates if d not in cnt]
    print(f"   theme dates with no mi_stock_scores run: {missing_dates or 'none'}")

    # ---- classify every non-Retired row ----
    pop = []
    n_retired = collections.Counter()
    for t in themes_all:
        d = t["theme_date"]
        if d not in dates:
            continue
        if t["stage"] == "Retired":
            n_retired[d] += 1
            continue
        tk = list(dict.fromkeys(t["tickers"] or []))
        r = {
            "date": d, "name": t["name"], "stage": t["stage"], "source": t["source"],
            "score": float(t["score"]), "rs_avg": t["rs_avg"], "tickers": tk,
            "n_stored": len(tk), "days_active": t["days_active"], "breadth": t["pct_above_20sma"],
        }
        data = {x: rs[d][x] for x in tk if x in rs[d]}
        r["n_data"] = len(data)
        r["vals_all"] = list(data.values())

        # --- S2 inputs (whole stored roster with data) ---
        r["s2_ok"] = (t["stage"] != "Fading") and len(data) >= 1

        # --- S1 classification ---
        if t["rs_avg"] is None:
            r["kind"] = "fixed_fading_branch" if t["stage"] == "Fading" else "fixed_rsavg_null_other"
        elif t["source"] == "shadow_promoted" and r["vals_all"] and \
                abs(sum(r["vals_all"]) / len(r["vals_all"]) - t["rs_avg"]) < 1e-6 and abs(t["score"] - t["rs_avg"]) < 1e-9:
            r["kind"] = "fixed_shadow_plainmean"
        elif t["rs_avg"] == 0:
            r["kind"] = "fixed_zero_momentum"
        else:
            r["kind"] = "engine_fed"
            strong = [v for v in data.values() if v >= 50]
            p = row_of.get((prev_of[d], t["name"]))
            cands = [("iii_stored_strong", strong)]
            if p is not None:
                pset = set(p["tickers"] or [])
                cands.append(("v_prev_inter_strong", [rs[d][x] for x in tk if x in pset and x in rs[d] and rs[d][x] >= 50]))
                cands.append(("vi_prev_strong", [rs[d][x] for x in (p["tickers"] or []) if x in rs[d] and rs[d][x] >= 50]))
            cands.append(("iv_stored_any", list(data.values())))
            hit = None
            for lab, vals in cands:
                if vals and abs(arm_A(vals) - t["rs_avg"]) <= 0.051:
                    hit = (lab, vals)
                    break
            if hit:
                r["set_label"], r["s1_vals"], r["verified"] = hit[0], hit[1], True
            else:
                vals = strong if strong else list(data.values())
                r["set_label"], r["s1_vals"], r["verified"] = "UNVERIFIED", vals, False
            if not r["s1_vals"]:
                r["kind"] = "fixed_no_data"
        pop.append(r)

    # ---------------------------------------------------------------------------------------------
    # 1. POPULATION
    # ---------------------------------------------------------------------------------------------
    print("=" * 100)
    print("1. POPULATION (stated before any result)")
    print(f"   dates: {len(dates)}  ({dates[0]} .. {dates[-1]});  non-Retired rows: {len(pop)};  Retired rows excluded: {sum(n_retired.values())}")
    per_date = collections.Counter(r["date"] for r in pop)
    print(f"   themes per date: min={min(per_date.values())} median={statistics.median(per_date.values())} max={max(per_date.values())}")
    kinds = collections.Counter(r["kind"] for r in pop)
    print("   S1 row kinds (does the trim feed the stored score?):")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"      {k:26s} {v:5d}   ({100*v/len(pop):.1f}%)")
    stages = collections.Counter(r["stage"] for r in pop)
    print("   stages: " + ", ".join(f"{k}={v}" for k, v in stages.most_common()))
    srcs = collections.Counter(r["source"] for r in pop)
    print("   sources: " + ", ".join(f"{k}={v}" for k, v in srcs.most_common()))

    fed = [r for r in pop if r["kind"] == "engine_fed"]
    ver = [r for r in fed if r["verified"]]
    print(f"   engine_fed rows: {len(fed)}; member set reproduces the stored rs_avg exactly (|diff|<=0.051): {len(ver)} ({100*len(ver)/len(fed):.1f}%); UNVERIFIED: {len(fed)-len(ver)}")
    print("   match label: " + ", ".join(f"{k}={v}" for k, v in collections.Counter(r['set_label'] for r in fed).most_common()))
    news = [r["score"] - min(r["rs_avg"] / 2, 50) for r in ver if r["source"] == "live"]
    nb = collections.Counter(round(x) for x in news)
    print(f"   sanity, implied news = stored_score - rs_avg/2 on verified live rows: min={min(news):.2f} max={max(news):.2f}; rounded histogram {dict(sorted(nb.items()))}")

    def bucket(n):
        return "1" if n == 1 else "2" if n == 2 else str(n) if n <= 5 else "6-10" if n <= 10 else "11-20" if n <= 20 else "21+"
    order = ["1", "2", "3", "4", "5", "6-10", "11-20", "21+"]
    print("   member-count distribution (number of themes), three bases:")
    print(f"      {'basis':46s}" + "".join(f"{b:>7s}" for b in order) + f"{'total':>8s}")
    for lab, fn, rows in [
        ("S2  stored members WITH same-date RS data (non-Fading)", lambda r: r["n_data"], [r for r in pop if r["s2_ok"]]),
        ("S1  engine scoring set size (engine_fed)", lambda r: len(r["s1_vals"]), fed),
        ("ALL stored members (all non-Retired rows)", lambda r: r["n_stored"], pop),
    ]:
        c = collections.Counter(bucket(fn(r)) for r in rows)
        print(f"      {lab:46s}" + "".join(f"{c.get(b,0):7d}" for b in order) + f"{len(rows):8d}")
    s2rows = [r for r in pop if r["s2_ok"]]
    lt3_s2 = sum(1 for r in s2rows if r["n_data"] < 3)
    lt3_s1 = sum(1 for r in fed if len(r["s1_vals"]) < 3)
    lt3_all = sum(1 for r in pop if r["n_stored"] < 3)
    print(f"   themes with <3 members: S2 basis (with data) {lt3_s2}/{len(s2rows)}; S1 scoring set {lt3_s1}/{len(fed)}; stored roster (all rows) {lt3_all}/{len(pop)}")
    print(f"      -> at <3 members the trim is a no-op (plain mean), so arms A=B=C for those themes.")
    print(f"   S2 excluded because Fading: {sum(1 for r in pop if r['stage']=='Fading')}; non-Fading with zero members-with-data: {sum(1 for r in pop if r['stage']!='Fading' and r['n_data']==0)}")
    print("   trim-relevant sizes (n=3,4,5 = where the drop is 33%/25%/20%): "
          f"S2 share of themes with n_data in 3..5 = {sum(1 for r in s2rows if 3 <= r['n_data'] <= 5)}/{len(s2rows)}; "
          f"S1 = {sum(1 for r in fed if 3 <= len(r['s1_vals']) <= 5)}/{len(fed)}")

    # ---------------------------------------------------------------------------------------------
    # 2. arm values
    # ---------------------------------------------------------------------------------------------
    for r in pop:
        # S2
        if r["s2_ok"]:
            v = r["vals_all"]
            r["s2_A"], r["s2_B"], r["s2_C"] = arm_A(v), arm_B(v), arm_C(v)
        # S1
        if r["kind"] == "engine_fed":
            v = r["s1_vals"]
            mA, mB, mC = arm_A(v), arm_B(v), arm_C(v)
            r["m_A"], r["m_B"], r["m_C"] = mA, mB, mC
            r["s1_A"] = r["score"]
            r["s1_B"] = r["score"] + 0.5 * (mB - mA)
            r["s1_C"] = r["score"] + 0.5 * (mC - mA)
        else:
            r["s1_A"] = r["s1_B"] = r["s1_C"] = r["score"]

    # ---------------------------------------------------------------------------------------------
    # 3. bias by basket size (how much the one-sided trim inflates the number)
    # ---------------------------------------------------------------------------------------------
    print("=" * 100)
    print("2. WHAT THE ONE-SIDED TRIM DOES TO THE NUMBER (RS points; A-B = inflation vs plain mean; C-B = what a symmetric trim does)")
    print("   dropped by the live rule: n=3:1(33%) n=4:1(25%) n=5:1(20%) n=6:2(33%) n=8:2(25%) n=10:2(20%) n=11-14:2 n=15-19:3 n=20+:4+")
    hdr = f"      {'n':>6s}{'themes':>8s}{'mean A-B':>10s}{'max A-B':>9s}{'mean C-B':>10s}{'mean |A-C|':>12s}"
    for lab, rows, nfn, ka, kb, kc in [
        ("S2 (/theme comp, all members with data)", s2rows, lambda r: r["n_data"], "s2_A", "s2_B", "s2_C"),
        ("S1 (engine momentum, strong members)", fed, lambda r: len(r["s1_vals"]), "m_A", "m_B", "m_C"),
    ]:
        print(f"   {lab}")
        print(hdr)
        by = collections.defaultdict(list)
        for r in rows:
            by[bucket(nfn(r))].append(r)
        for b in order:
            g = by.get(b)
            if not g:
                continue
            ab = [x[ka] - x[kb] for x in g]
            cb = [x[kc] - x[kb] for x in g]
            ac = [abs(x[ka] - x[kc]) for x in g]
            print(f"      {b:>6s}{len(g):8d}{statistics.mean(ab):10.2f}{max(ab):9.2f}{statistics.mean(cb):10.2f}{statistics.mean(ac):12.2f}")
        ab = [x[ka] - x[kb] for x in rows]
        print(f"      {'ALL':>6s}{len(rows):8d}{statistics.mean(ab):10.2f}{max(ab):9.2f}{statistics.mean([x[kc]-x[kb] for x in rows]):10.2f}{statistics.mean([abs(x[ka]-x[kc]) for x in rows]):12.2f}")
    offs = [r["s2_A"] - r["rs_avg"] for r in ver if r["s2_ok"]]
    print(f"   Definition gap: /theme comp (all members, arm A) minus the SAME night's stored rs_avg (strong members, arm A), verified rows: "
          f"n={len(offs)} mean={statistics.mean(offs):+.2f} median={statistics.median(offs):+.2f} min={min(offs):+.2f} max={max(offs):+.2f}")
    print("      (/theme's delta = comp(tonight) - prior night's stored rs_avg, briefing.py:_compute_scored_themes; this is the built-in offset in that delta.)")

    # ---------------------------------------------------------------------------------------------
    # 4. per-date rank comparisons
    # ---------------------------------------------------------------------------------------------
    def per_date_table(title, rows_by_date, ka, kb, kc, keep_movers):
        print("=" * 100)
        print(title)
        print(f"   {'date':<11s}{'n':>4s} | {'Spearman':>17s} | {'top10 overlap':>15s} | {'movers>=3 places':>17s} | {'tied-A':>6s}")
        print(f"   {'':<11s}{'':>4s} | {'A-B':>8s}{'A-C':>9s} | {'A-B':>7s}{'A-C':>8s} | {'A-B':>8s}{'A-C':>9s} | {'names':>6s}")
        agg = collections.defaultdict(list)
        movers = {"B": [], "C": []}
        for d in dates:
            rows = rows_by_date.get(d, [])
            if len(rows) < 3:
                continue
            cb, cc = compare_arms(rows, ka, kb), compare_arms(rows, ka, kc)
            ties = sum(1 for k, cnt_ in collections.Counter(round(r[ka], 9) for r in rows).items() if cnt_ > 1)
            tied_names = sum(cnt_ for k, cnt_ in collections.Counter(round(r[ka], 9) for r in rows).items() if cnt_ > 1)
            print(f"   {d:<11s}{cb['n']:4d} | {cb['spearman']:8.4f}{cc['spearman']:9.4f} | {cb['top10']:7d}{cc['top10']:8d} | {cb['movers3']:8d}{cc['movers3']:9d} | {tied_names:6d}")
            agg["sB"].append(cb["spearman"]); agg["sC"].append(cc["spearman"])
            agg["tB"].append(cb["top10"]); agg["tC"].append(cc["top10"])
            agg["mB"].append(cb["movers3"]); agg["mC"].append(cc["movers3"])
            agg["n"].append(cb["n"]); agg["tied"].append(tied_names)
            byname = {r["name"]: r for r in rows}
            for lab, cmp_, kx in (("B", cb, kb), ("C", cc, kc)):
                for nm, mv in cmp_["moves"].items():
                    r = byname[nm]
                    movers[lab].append((mv, d, nm, r, cmp_["oa"][nm], cmp_["ox"][nm], r[ka], r[kx]))
        k = len(agg["n"])
        tot_n = sum(agg["n"])
        print(f"   {'MEAN':<11s}{statistics.mean(agg['n']):4.0f} | {statistics.mean(agg['sB']):8.4f}{statistics.mean(agg['sC']):9.4f} | {statistics.mean(agg['tB']):7.1f}{statistics.mean(agg['tC']):8.1f} | {statistics.mean(agg['mB']):8.1f}{statistics.mean(agg['mC']):9.1f} | {statistics.mean(agg['tied']):6.1f}")
        print(f"   {'MIN':<11s}{'':4s} | {min(agg['sB']):8.4f}{min(agg['sC']):9.4f} | {min(agg['tB']):7d}{min(agg['tC']):8d} | {min(agg['mB']):8d}{min(agg['mC']):9d} |")
        print(f"   {'TOTAL':<11s}{tot_n:4d} | {'':17s} | {'':15s} | {sum(agg['mB']):8d}{sum(agg['mC']):9d} | share of theme-days moving >=3: A-B {100*sum(agg['mB'])/tot_n:.1f}%  A-C {100*sum(agg['mC'])/tot_n:.1f}%")
        return movers

    def print_movers(title, movers, cols):
        print("-" * 100)
        print(title)
        print(f"   {'d rank':>6s} {'date':<11s} {'rankA':>5s}->{'rankX':<5s} {'A':>7s} {'X':>7s}  {'stored':>6s} {'usedS1':>6s} {'dataS2':>6s}  {'stage':<12s}{'src':<8s} name")
        for mv, d, nm, r, ra, rx, va, vx in sorted(movers, key=lambda m: (-m[0], m[1], m[2]))[:10]:
            used = len(r["s1_vals"]) if r["kind"] == "engine_fed" else 0
            print(f"   {mv:6d} {d:<11s} {ra:5d}->{rx:<5d} {va:7.2f} {vx:7.2f}  {r['n_stored']:6d} {used:6d} {r['n_data']:6d}  {r['stage']:<12s}{r['source'][:7]:<8s} {nm[:70]}")

    by_all = collections.defaultdict(list)
    by_fed = collections.defaultdict(list)
    by_fedv = collections.defaultdict(list)
    by_s2 = collections.defaultdict(list)
    for r in pop:
        by_all[r["date"]].append(r)
        if r["kind"] == "engine_fed":
            by_fed[r["date"]].append(r)
            if r["verified"]:
                by_fedv[r["date"]].append(r)
        if r["s2_ok"]:
            by_s2[r["date"]].append(r)

    mv_all = per_date_table("3. S1-ALL  (PRIMARY): stored mi_themes.score, all non-Retired rows; trim component swapped, news + fixed rows held. Dashboard-style ranking.",
                            by_all, "s1_A", "s1_B", "s1_C", True)
    print_movers("   10 biggest movers S1-ALL, A -> B (plain mean)", mv_all["B"], None)
    print_movers("   10 biggest movers S1-ALL, A -> C (symmetric trim)", mv_all["C"], None)

    mv_fed = per_date_table("4. S1-FED  (sensitivity): only rows whose stored score the trim feeds (fixed rows removed from the ranking)",
                            by_fed, "s1_A", "s1_B", "s1_C", True)
    print_movers("   10 biggest movers S1-FED, A -> B", mv_fed["B"], None)
    print_movers("   10 biggest movers S1-FED, A -> C", mv_fed["C"], None)

    per_date_table("4b. S1-FED-VERIFIED (sensitivity): as 4 but only rows whose reconstructed member set reproduces the stored rs_avg",
                   by_fedv, "s1_A", "s1_B", "s1_C", False)

    mv_s2 = per_date_table("5. S2  (SECONDARY): the /theme ranking -- comp over ALL stored members with data, non-Fading, non-Retired",
                           by_s2, "s2_A", "s2_B", "s2_C", True)
    print_movers("   10 biggest movers S2, A -> B", mv_s2["B"], None)
    print_movers("   10 biggest movers S2, A -> C", mv_s2["C"], None)

    # ---------------------------------------------------------------------------------------------
    # 6. does the size of the basket predict who moves?  (the structural question)
    # ---------------------------------------------------------------------------------------------
    print("=" * 100)
    print("6. DIRECTION OF THE MOVES (S2, A -> B): do small baskets gain rank from the one-sided trim?  (rank_A - rank_B > 0 means A ranks the theme HIGHER than plain mean does)")
    gain = collections.defaultdict(list)
    for d in dates:
        rows = by_s2.get(d, [])
        if len(rows) < 3:
            continue
        cb = compare_arms(rows, "s2_A", "s2_B")
        for r in rows:
            gain[bucket(r["n_data"])].append(cb["ox"][r["name"]] - cb["oa"][r["name"]])   # + => A ranks higher (smaller rank number)
    print(f"      {'n_data':>7s}{'theme-days':>11s}{'mean places A ranks higher than B':>36s}{'share ranked higher by A':>26s}{'share lower':>13s}")
    for b in order:
        g = gain.get(b)
        if g:
            print(f"      {b:>7s}{len(g):11d}{statistics.mean(g):36.2f}{100*sum(1 for x in g if x>0)/len(g):25.1f}%{100*sum(1 for x in g if x<0)/len(g):12.1f}%")


    # ---------------------------------------------------------------------------------------------
    # 7. EXTRA (post-hoc): tie-robustness of the mover count
    # ---------------------------------------------------------------------------------------------
    print("=" * 100)
    print("7. EXTRA (post-hoc, not the pre-registered metric): is the mover count an artefact of tie-breaking?")
    print("   The live score is rounded to 0.1, so many themes tie in A; arms B/C computed unrounded break those ties by value, A breaks them by name.")
    print("   (i) X rounded to 0.1 like the live engine would;  (ii) movers measured on AVERAGE ranks (ties share a rank).  mean movers>=3 per date:")
    print(f"      {'population':<12s}{'as reported (A-B / A-C)':>26s}{'(i) rounded (A-B / A-C)':>26s}{'(ii) avg-rank (A-B / A-C)':>28s}")
    for lab, byd in (("S1-ALL", by_all), ("S1-FED", by_fed)):
        rep = {"B": [], "C": []}; rnd_ = {"B": [], "C": []}; avg_ = {"B": [], "C": []}
        for d in dates:
            rows = byd.get(d, [])
            if len(rows) < 3:
                continue
            for r in rows:
                r["s1_B_r"] = round(r["s1_B"], 1); r["s1_C_r"] = round(r["s1_C"], 1)
            for L_, kx, kxr in (("B", "s1_B", "s1_B_r"), ("C", "s1_C", "s1_C_r")):
                rep[L_].append(compare_arms(rows, "s1_A", kx)["movers3"])
                rnd_[L_].append(compare_arms(rows, "s1_A", kxr)["movers3"])
                ra = avg_rank([(r["name"], r["s1_A"]) for r in rows]); rx = avg_rank([(r["name"], r[kx]) for r in rows])
                avg_[L_].append(sum(1 for r in rows if abs(ra[r["name"]] - rx[r["name"]]) >= 3))
        m = statistics.mean
        print(f"      {lab:<12s}{m(rep['B']):>13.1f} /{m(rep['C']):>8.1f}{m(rnd_['B']):>14.1f} /{m(rnd_['C']):>8.1f}{m(avg_['B']):>15.1f} /{m(avg_['C']):>8.1f}")

    # ---------------------------------------------------------------------------------------------
    # 8. EXTRA (post-hoc): how much does the trim's own bias move night to night?  (stage-transition exposure proxy)
    # ---------------------------------------------------------------------------------------------
    print("=" * 100)
    print("8. EXTRA (post-hoc proxy for stage-transition exposure; NOT a replay of the stage logic)")
    print("   Stage flips key on smooth_delta = score - avg(recent scores) with thresholds +8 / -8 (recovery +5), theme_engine.py:3878-3887.")
    print("   A constant inflation cancels in a delta; only the NIGHT-TO-NIGHT CHANGE of the bias 0.5*(A-B) leaks into it. Score points, same theme on consecutive population dates, verified member sets:")
    prev_row = {(r["date"], r["name"]): r for r in pop}
    dd, dscore = [], []
    for i in range(1, len(dates)):
        for r in by_fedv.get(dates[i], []):
            q = prev_row.get((dates[i - 1], r["name"]))
            if q is not None and q["kind"] == "engine_fed" and q.get("verified"):
                dd.append(abs(0.5 * (r["m_A"] - r["m_B"]) - 0.5 * (q["m_A"] - q["m_B"])))
                dscore.append(abs(r["score"] - q["score"]))
    def pct(xs, p):
        xs = sorted(xs); return xs[min(len(xs) - 1, int(p * len(xs)))]
    print(f"      consecutive-night pairs: {len(dd)}")
    print(f"      |night-to-night change of trim bias|  p50={pct(dd,.5):.2f} p90={pct(dd,.9):.2f} p99={pct(dd,.99):.2f} max={max(dd):.2f};  share >=3 pts: {100*sum(1 for x in dd if x>=3)/len(dd):.1f}%  >=5: {100*sum(1 for x in dd if x>=5)/len(dd):.1f}%  >=8: {100*sum(1 for x in dd if x>=8)/len(dd):.1f}%")
    print(f"      |night-to-night change of the stored score| p50={pct(dscore,.5):.2f} p90={pct(dscore,.9):.2f} p99={pct(dscore,.99):.2f} max={max(dscore):.2f}")


    # ---------------------------------------------------------------------------------------------
    # 9. EXTRA (post-hoc): the dashboard's DEFAULT view is Accelerating + Mainstream only
    #    (dashboard/theme_rank_evolution.py:96,104). Same S1 arms, ranking restricted to those stages.
    # ---------------------------------------------------------------------------------------------
    print("=" * 100)
    print("9. EXTRA (post-hoc): S1 restricted to the dashboard's DEFAULT stage filter (Accelerating + Mainstream), dashboard/theme_rank_evolution.py:96,104")
    by_dash = collections.defaultdict(list)
    for r in pop:
        if r["stage"] in ("Accelerating", "Mainstream"):
            by_dash[r["date"]].append(r)
    agg9 = collections.defaultdict(list)
    for d in dates:
        rows = by_dash.get(d, [])
        if len(rows) < 3:
            continue
        cb, cc = compare_arms(rows, "s1_A", "s1_B"), compare_arms(rows, "s1_A", "s1_C")
        agg9["n"].append(cb["n"]); agg9["sB"].append(cb["spearman"]); agg9["sC"].append(cc["spearman"])
        agg9["tB"].append(cb["top10"]); agg9["tC"].append(cc["top10"]); agg9["mB"].append(cb["movers3"]); agg9["mC"].append(cc["movers3"])
    m = statistics.mean
    print(f"   dates={len(agg9['n'])}  themes/date mean={m(agg9['n']):.1f} (min {min(agg9['n'])}, max {max(agg9['n'])});  of these, fixed (not trim-fed) rows: {sum(1 for r in pop if r['stage'] in ('Accelerating','Mainstream') and r['kind']!='engine_fed')}")
    print(f"   Spearman   A-B mean {m(agg9['sB']):.4f} (min {min(agg9['sB']):.4f})   A-C mean {m(agg9['sC']):.4f} (min {min(agg9['sC']):.4f})")
    print(f"   top10 overlap  A-B mean {m(agg9['tB']):.1f} (min {min(agg9['tB'])})   A-C mean {m(agg9['tC']):.1f} (min {min(agg9['tC'])})")
    print(f"   movers>=3 per date  A-B mean {m(agg9['mB']):.1f}   A-C mean {m(agg9['mC']):.1f}   (share of theme-days: A-B {100*sum(agg9['mB'])/sum(agg9['n']):.1f}%  A-C {100*sum(agg9['mC'])/sum(agg9['n']):.1f}%)")


    # ---------------------------------------------------------------------------------------------
    # 10. EXTRA (post-hoc): rows whose stored score is on a DIFFERENT scale/basis sitting in the stored top-10
    # ---------------------------------------------------------------------------------------------
    print("=" * 100)
    print("10. EXTRA (post-hoc): what occupies the top-10 of the STORED score (the dashboard's default metric) -- shadow_promoted rows are a plain mean 0-100 with no news; live rows are rs/2 + news(0..30) so cap at 80")
    cnt_sh, cnt_fb, cnt_top = [], [], 0
    live_max = max(r["score"] for r in pop if r["kind"] == "engine_fed")
    sh_scores = [r["score"] for r in pop if r["kind"] == "fixed_shadow_plainmean"]
    for d in dates:
        rows = sorted(by_all.get(d, []), key=lambda r: (-r["score"], r["name"]))[:10]
        cnt_sh.append(sum(1 for r in rows if r["kind"] == "fixed_shadow_plainmean"))
        cnt_fb.append(sum(1 for r in rows if r["kind"] == "fixed_fading_branch"))
    print(f"   max stored score among trim-fed live rows: {live_max:.1f};  shadow_promoted rows: n={len(sh_scores)}, score min/median/max = {min(sh_scores):.1f}/{statistics.median(sh_scores):.1f}/{max(sh_scores):.1f}; share above {live_max:.0f}: {100*sum(1 for x in sh_scores if x>live_max)/len(sh_scores):.1f}%")
    print(f"   per date, of the 10 highest stored scores: shadow_promoted rows mean {statistics.mean(cnt_sh):.2f} (max {max(cnt_sh)}, dates with >=1: {sum(1 for x in cnt_sh if x>0)}/20); Fading-branch rows mean {statistics.mean(cnt_fb):.2f} (max {max(cnt_fb)})")

    print("=" * 100)
    print("END")


if __name__ == "__main__":
    main()
