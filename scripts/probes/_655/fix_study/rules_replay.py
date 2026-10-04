"""#655 — replay of THREE candidate engine rules on the captured 2026-10-02 board (read-only).

RULES, STATED BEFORE ANY NUMBER WAS COMPUTED (parameters fixed here, not tuned on results):

  RULE A  "tape retire"      A theme whose member cohesion is below its size-matched random
                             basket's p95 (the signed G3 maths, compute_g3 — the ONLY tape read that
                             works at 2-3 members) on K_A = 3 CONSECUTIVE nightly reads is retired
                             (engine-drop tombstone, members released). K_A = 3 because 6 verdicts
                             sit within +-0.05 of chance and flip night to night, and 3 reads is a
                             newborn's grace. The threshold is the signed p95 itself — no new number.
                             Site: a pass right after Step 2a's carry-forward strip (theme_engine.py
                             ~:9548), pure compute_g3 on the board + a per-theme streak persisted in
                             its own audit row. ~80-120 lines. Detector change -> CHANGE_PROCESS.

  RULE B  "no grace under 3" A Fading theme with fewer than THEME_COVERAGE_MIN (3) members retires
                             the night it is weak-Fading; the FADING_RETIRE_AFTER = 5 grace applies
                             only to themes with >= 3 members (a 2-member theme has nothing the
                             engine can read or recover). Site: theme_engine.py :3826-3830, one extra
                             condition. ~3 lines. Detector change -> CHANGE_PROCESS.

  RULE C  "tape birth floor" A new cohort is born only if its founders' cohesion beats the
                             size-matched random basket's p95 (same compute_g3 maths, one-theme call);
                             otherwise it is recorded in the birth ledger as held and may re-sight.
                             Site: _validate_new_themes_at_birth :2802 (Lane 1) + promote_shadow_themes
                             :2460 first crossings. ~40-60 lines. Detector change -> CHANGE_PROCESS.

Honest limits of the 60-day capture:
  * ONE excess window (60 sessions ending 10-01, for the 10-02 read). Replays on the 09-30/10-01
    boards reuse it (58-59 of 60 sessions shared) — the nightly fail lists are the ground truth there.
  * K_A = 3 is checkable only for the 10-02 night (3 lists); for 10-01 only K = 2.
  * Rule C's founders test uses a window mostly AFTER birth for older themes -> its false-kill cost
    is a LOWER BOUND; the <= 10-session births are the clean read.
  * compute_g3 draws controls from one RNG stream — removing themes shifts every later theme's
    draws; survivors can flip for no reason. Every after-state lists those flips as DRIFT.
"""
import pickle, sys, re, collections, json
from datetime import date
import numpy as np
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import theme_correctness as tc

K_A = 3
SCRATCH = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/"
OUT = SCRATCH + "655_study/"
d = pickle.load(open(SCRATCH + "655_capture.pkl", "rb"))
themes, meta, scores, sector, excess, history, report = (
    d["themes"], d["board_meta"], d["scores"], d["sector"], d["excess"], d["history"], d["report"])
meta_by = {m["name"]: m for m in meta}
usable = tc.usable_set(excess)
lines: list[str] = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); lines.append(s)

# ── nightly lists ───────────────────────────────────────────────────────────────────────────────
txt = open(SCRATCH + "655_rows.txt").read()
nights = {}
for dt, g3, g4 in re.findall(r"(\d{4}-\d{2}-\d{2}) \d\d:.*?\n  G3 fail: (\[.*?\])\n  G4 small: (\[.*?\])", txt, re.S):
    nights[date.fromisoformat(dt)] = (set(eval(g3)), set(eval(g4)))
N0930, N1001, N1002 = date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)

# ── history -> boards ──────────────────────────────────────────────────────────────────────────
by_date = collections.defaultdict(list)
hist = collections.defaultdict(dict)
for r in history:
    by_date[r["theme_date"]].append(r)
    hist[r["name"]][r["theme_date"]] = r
all_dates = sorted(by_date)

def board_at(dt):
    """Non-Retired rows for that date, in stored order (approximates db.get_active_themes)."""
    return [{"name": r["name"], "stage": r["stage"], "tickers": list(r["tickers"] or [])}
            for r in by_date[dt] if r["stage"] != "Retired"]

boards = {N0930: board_at(N0930), N1001: board_at(N1001), N1002: themes}
P("board sizes from history: 09-30", len(boards[N0930]), "(nightly said 129) | 10-01", len(boards[N1001]),
  "(nightly 131) | 10-02 capture", len(themes), "(nightly 133)")
# the 09-30 gap: a name active via the 7-day recency cap but without a 09-30 row?
names0930 = {t["name"] for t in boards[N0930]}
cands = [n for n in nights[N0930][0] | nights[N0930][1] if n not in names0930]
P("  09-30 nightly-list names with no 09-30 row:", cands)

def run(board):
    rep = tc.build_correctness_report(board, excess, scores, sector)
    g3v = {r["name"]: r["pass_g3"] for r in rep["g3"]["themes"]}
    return rep, g3v

def fmt(rep):
    g1, g2, g3, g4 = rep["g1"], rep["g2"], rep["g3"], rep["g4"]
    return (f"G1 {g1['pass']}/{g1['n']}={g1['rate_pct']}% {'PASS' if g1['pass_bar'] else 'FAIL'} | "
            f"G2 {g2['flagged']}/{g2['n']}={g2['rate_pct']}% {'PASS' if g2['pass_bar'] else 'FAIL'} | "
            f"G3 {g3['pass']}/{g3['n_judgeable']}={g3['rate_pct']}% {'PASS' if g3['pass_bar'] else 'FAIL'} | "
            f"G4 {g4['small']}/{g4['n_board']}={g4['rate_pct']}% {'PASS' if g4['pass_bar'] else 'FAIL'}")

base_rep, base_g3 = run(themes)
P("\nBASELINE 10-02 capture:", fmt(base_rep))
assert base_rep["g3"]["pass"] == report["g3"]["pass"], "capture report mismatch"

def homes_of(board):
    h = collections.defaultdict(set)
    for t in board:
        for m in t["tickers"]: h[m].add(t["name"])
    return h

def after(label, board, removed, base_verdicts, base_board):
    rep, g3v = run(board)
    P(f"\n== {label}: removes {len(removed)} -> {fmt(rep)}")
    drift = [(n, base_verdicts[n], g3v[n]) for n in g3v if n in base_verdicts and g3v[n] != base_verdicts[n]]
    P(f"   RNG drift among untouched survivors: {len(drift)}", drift if drift else "")
    hb = homes_of(board)
    for n in removed:
        t = next(x for x in base_board if x["name"] == n)
        m = meta_by.get(n, {})
        homeless = [tk for tk in t["tickers"] if not hb.get(tk)]
        P(f"   - {n[:58]:58s} sz={len(t['tickers'])} {t['stage'][:2]} rs_avg={m.get('rs_avg')} days={m.get('days_active')} "
          f"coh={'%.2f' % base_g3_coh.get(n, float('nan'))} homeless={homeless}")
    return rep, g3v

base_g3_coh = {r["name"]: (r["cohesion"] if r["cohesion"] is not None else float("nan")) for r in base_rep["g3"]["themes"]}

# ── RULE A ───────────────────────────────────────────────────────────────────────────────────────
P("\n################ RULE A — tape retire, K=3 consecutive G3 fails")
capture_fail = set(base_rep["g3"]["fail_list"])
f0930, f1001, f1002 = nights[N0930][0], nights[N1001][0], nights[N1002][0]
P("per-night G3 fail counts: 09-30", len(f0930), "10-01", len(f1001), "10-02 nightly", len(f1002), "10-02 capture", len(capture_fail))
P("  09-30 ∩ 10-01 =", len(f0930 & f1001), "| all three nightly =", len(f0930 & f1001 & f1002),
  "| nightly 10-02 vs capture symmetric diff:", sorted(f1002 ^ capture_fail))
A_set = sorted(f0930 & f1001 & capture_fail)
P(f"  K=3 retire set (fails 09-30, 10-01 AND the 10-02 capture read): {len(A_set)}")
for n in A_set: P("    ", n)
P("  same set using the nightly 10-02 list instead of the capture?", sorted(f0930 & f1001 & f1002) == A_set)
# which fails are NOT retired (young / knife-edge) and how many consecutive nights each has
for n in sorted(capture_fail - set(A_set)):
    streak = int(n in f1001) + (int(n in f0930) if n in f1001 else 0)
    m = meta_by[n]
    P(f"    kept (streak {1+streak} <3): {n[:55]:55s} sz={len(next(t for t in themes if t['name']==n)['tickers'])} {m['stage'][:2]} days={m['days_active']} coh-p95={base_g3_coh[n]-next(r['c1_p95'] for r in base_rep['g3']['themes'] if r['name']==n):+.3f}")
A_board = [t for t in themes if t["name"] not in A_set]
A_rep, A_g3 = after("RULE A on 10-02", A_board, A_set, base_g3, themes)
# G1/G2 row-level effect of removing Industrial Construction (the only k>=4 theme)
g12 = tc.compute_g1_g2(themes, excess)
ic_rows = [r for r in g12["rows"] if r.theme.startswith("Industrial Construction")]
P(f"   Industrial Construction G1/G2 rows: {len(ic_rows)} judgeable={sum(1 for r in ic_rows if r.own is not None)} "
  f"g1-pass={sum(1 for r in ic_rows if r.own is not None and r.own >= 0.35)} misfiled={sum(1 for r in ic_rows if r.misfiled)}")
# robustness: 10-01 night with K=2 (only two prior lists exist)
A1001 = sorted(f0930 & f1001)
P(f"\n   10-01 night, K=2 (the most the lists allow): would retire {len(A1001)} — identical to the K=3 set? {A1001 == A_set}")
b1001 = boards[N1001]
rep1001, g3v1001 = run(b1001)
P("   10-01 board replayed on the 10-02 window (caveat):", fmt(rep1001), "| nightly read was G3 117/131 G4 16/131")
b1001A = [t for t in b1001 if t["name"] not in A1001]
repA1001, _ = run(b1001A)
small1001 = nights[N1001][1]
P(f"   10-01 after A (nightly G4 list minus retired): small {len(small1001 - set(A1001))}/{len(b1001)-len(A1001)} = "
  f"{100*len(small1001 - set(A1001))/(len(b1001)-len(A1001)):.1f}% | G3 (replay) {fmt(repA1001)}")

# ── RULE B ───────────────────────────────────────────────────────────────────────────────────────
P("\n################ RULE B — a Fading theme under 3 members retires at once (no 5-night grace)")
B_set = sorted(t["name"] for t in themes if t["stage"] == "Fading" and len(t["tickers"]) < 3)
B_board = [t for t in themes if t["name"] not in B_set]
B_rep, B_g3 = after("RULE B on 10-02", B_board, B_set, base_g3, themes)
# robustness on 09-30 and 10-01: exact G4 from the nightly small lists + history stages
for dt in (N0930, N1001):
    smalls = nights[dt][1]
    stage_of = {r["name"]: r["stage"] for r in by_date[dt]}
    fading_small = sorted(n for n in smalls if stage_of.get(n) == "Fading")
    n_board = 129 if dt == N0930 else 131
    P(f"   {dt}: G4 small {len(smalls)}/{n_board}; Fading among them {len(fading_small)} -> after B "
      f"{len(smalls)-len(fading_small)}/{n_board-len(fading_small)} = {100*(len(smalls)-len(fading_small))/(n_board-len(fading_small)):.1f}% "
      f"{'PASS' if 100*(len(smalls)-len(fading_small))/(n_board-len(fading_small)) <= 10 else 'FAIL'}")
    P(f"      stages of the non-Fading smalls: {collections.Counter(stage_of.get(n) for n in smalls if stage_of.get(n) != 'Fading')}")
    missing = [n for n in smalls if n not in stage_of]
    if missing: P("      (no history row that date:", missing, ")")
# COST from history: <3-member Fading rows later followed by a non-Fading row of the same name
P("\n   COST (60-day history): 2-member Fading themes that later RECOVERED (non-Fading row after a <3-member Fading row)")
recov = []
shell_names = set()
for name, rows in hist.items():
    ds = sorted(rows)
    for i, dd in enumerate(ds):
        r = rows[dd]
        if r["stage"] == "Fading" and 0 < len(r["tickers"] or []) < 3:
            shell_names.add(name)
            later = [rows[x] for x in ds[i+1:] if rows[x]["stage"] not in ("Fading", "Retired") and rows[x]["tickers"]]
            if later:
                nxt = later[0]
                grew = any(len(rows[x]["tickers"] or []) >= 3 for x in ds[i+1:])
                recov.append((name, dd, nxt["theme_date"], nxt["stage"], len(nxt["tickers"]), grew))
                break
P(f"   themes that were ever a <3-member Fading shell: {len(shell_names)}; of those later recovered to non-Fading: {len(recov)}; "
  f"recovered AND later reached >=3 members: {sum(1 for x in recov if x[5])}")
for x in recov: P("     ", x)
# how long do shells live?
spans = []
for name in shell_names:
    rows = hist[name]; ds = sorted(rows)
    run_len = 0; best = 0
    for dd in ds:
        r = rows[dd]
        if r["stage"] == "Fading" and 0 < len(r["tickers"] or []) < 3: run_len += 1; best = max(best, run_len)
        else: run_len = 0
    spans.append(best)
P("   shell streak lengths (nights as a <3-member Fading row), distribution:", sorted(collections.Counter(spans).items()))
P("   #491 interaction: no guard drops a 1-member theme; a rehome move out of a pair leaves a 1-member Fading remnant "
  "that today rides up to 5 nights as G4-small. Rule B closes that. Caps 18/night, 3/target -> ~3 nights to drain 41 candidates.")

# ── A + B ────────────────────────────────────────────────────────────────────────────────────────
P("\n################ RULE A + RULE B combined")
AB_set = sorted(set(A_set) | set(B_set))
AB_board = [t for t in themes if t["name"] not in AB_set]
AB_rep, _ = after("A+B on 10-02", AB_board, AB_set, base_g3, themes)
# 10-01 robustness for A(K=2)+B
smalls = nights[N1001][1]; stage_of = {r["name"]: r["stage"] for r in by_date[N1001]}
rem = set(A1001) | {n for n in smalls if stage_of.get(n) == "Fading"}
fading_small_all_1001 = [t["name"] for t in b1001 if t["stage"] == "Fading" and len(t["tickers"]) < 3]
rem_all = set(A1001) | set(fading_small_all_1001)
nb = len(b1001) - len(rem_all)
P(f"   10-01: A(K=2)+B removes {len(rem_all)} -> G4 small {len(smalls - rem_all)}/{nb} = {100*len(smalls-rem_all)/nb:.1f}% ; "
  f"G3 (replay on 10-02 window) {fmt(run([t for t in b1001 if t['name'] not in rem_all])[0])}")

# ── RULE C ───────────────────────────────────────────────────────────────────────────────────────
P("\n################ RULE C — tape birth floor (founders' cohesion must beat the one-theme random p95)")
first_hist = all_dates[0]
def founders(name):
    ds = sorted(hist[name]); d0 = ds[0]
    return d0, list(hist[name][d0]["tickers"] or [])
def one_theme_g3(tks):
    r = tc.compute_g3([{"name": "_x", "stage": "Nascent", "tickers": tks}], excess, usable, scores, sector)["themes"][0]
    return r["cohesion"], r["c1_p95"], r["pass_g3"]
sessions_idx = {dd: i for i, dd in enumerate(all_dates)}
C_rows = []
for t in themes:
    d0, f = founders(t["name"])
    if d0 == first_hist:  # history starts 08-05: birth unobservable
        C_rows.append((t["name"], d0, None, None, None, None, "birth-before-history")); continue
    coh, p95, ok = one_theme_g3(f)
    age = len(all_dates) - sessions_idx[d0]  # sessions since birth (incl. birth night)
    C_rows.append((t["name"], d0, len(f), coh, p95, ok, age))
C_fail = [r[0] for r in C_rows if r[5] is False]
C_unj = [r[0] for r in C_rows if r[5] is None and r[6] != "birth-before-history"]
P(f"   board themes with an observable birth: {sum(1 for r in C_rows if r[6] != 'birth-before-history')}; founders fail the floor: {len(C_fail)}; "
  f"unjudgeable founders (<2 usable): {len(C_unj)}; birth before history: {sum(1 for r in C_rows if r[6]=='birth-before-history')}")
P("   NOTE: one-theme compute_g3 draws its own p95 (fresh RNG) — exactly what the engine would do at birth; it differs from the board run's p95.")
P("   NOTE: founders are tested on the 10-02 window; for births older than ~10 sessions the window is mostly AFTER birth -> false-kill cost below is a LOWER BOUND.")
C_board = [t for t in themes if t["name"] not in C_fail]
C_rep, _ = after("RULE C on 10-02 (remove board themes whose founders fail)", C_board, C_fail, base_g3, themes)
# cost: of the removed, which are currently PASSING G3 / big / Mainstream / high rs_avg
P("   false-kill read, board: removed themes that currently PASS G3:",
  [(n, len(next(t for t in themes if t['name']==n)['tickers']), meta_by[n]['stage'], meta_by[n]['rs_avg']) for n in C_fail if base_g3.get(n)])
# cost across ALL births in history (not just the board): births whose founders fail but that became 'real'
P("\n   COST over ALL births 08-06..10-02 in history (lower bound — window bias):")
births = []
for name, rows in hist.items():
    ds = sorted(rows); d0 = ds[0]
    if d0 == first_hist: continue
    f = list(rows[d0]["tickers"] or [])
    if len(f) < 2: continue
    coh, p95, ok = one_theme_g3(f)
    maxsz = max(len(rows[x]["tickers"] or []) for x in ds)
    stages = {rows[x]["stage"] for x in ds}
    lived = sum(1 for x in ds if rows[x]["stage"] != "Retired")
    age = len(all_dates) - sessions_idx[d0]
    births.append(dict(name=name, d0=d0, k=len(f), coh=coh, p95=p95, ok=ok, maxsz=maxsz,
                       mainstream="Mainstream" in stages, lived=lived, age=age, on_board=name in meta_by))
judg = [b for b in births if b["ok"] is not None]
P(f"   births with judgeable founders: {len(judg)} of {len(births)}; founders fail: {sum(1 for b in judg if not b['ok'])}")
def real(b): return b["maxsz"] >= 4 or (b["mainstream"] and b["lived"] >= 10)
for lab, sel in (("ALL ages", judg), ("<=10 sessions old (clean window)", [b for b in judg if b["age"] <= 10])):
    fails = [b for b in sel if not b["ok"]]; passes = [b for b in sel if b["ok"]]
    P(f"   [{lab}] n={len(sel)} fail={len(fails)} of which became real (>=4 members or Mainstream>=10 nights)={sum(1 for b in fails if real(b))} ; "
      f"pass={len(passes)} of which real={sum(1 for b in passes if real(b))}")
    for b in fails:
        if real(b): P(f"      FALSE-KILL: {b['name'][:60]} born {b['d0']} k={b['k']} coh={b['coh']:.2f} p95={b['p95']:.2f} maxsz={b['maxsz']} mainstream={b['mainstream']} lived={b['lived']} on_board={b['on_board']}")
P("   births by founder size:", sorted(collections.Counter(b["k"] for b in births).items()))
P("   born-at-2 that ever reached >=4 members:", sum(1 for b in births if b["k"] == 2 and b["maxsz"] >= 4), "of", sum(1 for b in births if b["k"] == 2))

# ── forming-vs-incoherent diagnostic for the young G3 fails (NOT a rule, NOT a measure) ──────────
P("\n################ DIAGNOSTIC — are the young G3 fails FORMING (recent co-movement) or incoherent?  (20-session cohesion vs 60)")
def coh_window(tks, n):
    ms = [m for m in tks if m in usable]
    if len(ms) < 2: return None
    M = np.vstack([excess[m][-n:] for m in ms])
    M = np.where(np.isfinite(M), M, np.nan)
    C = np.ma.corrcoef(np.ma.masked_invalid(M)).filled(np.nan)
    k = len(ms); return float((np.nansum(C) - k) / (k * (k - 1)))
for n in sorted(capture_fail):
    t = next(x for x in themes if x["name"] == n); m = meta_by[n]
    P(f"   {n[:55]:55s} sz={len(t['tickers'])} {m['stage'][:2]} days={m['days_active']:2d} coh60={coh_window(t['tickers'],60):.2f} coh20={coh_window(t['tickers'],20):.2f} coh10={coh_window(t['tickers'],10):.2f}")

# ── the two BUG FIXES (not rules) ────────────────────────────────────────────────────────────────
P("\n################ BUG FIXES (outside the rule table)")
P("  E  promote lane: a Retired tombstone counts as `prior` (:2515-2520) so the join gate is skipped -> 'Defense & Space Systems Satellite Solutions' re-minted 10-02 over its 'Aerospace Engine…' twin. Board effect: 1 G3 fail.")
P("  F  _count_consecutive_fading (:1621) counts only rs_avg=None rows, so a Fading theme that keeps one strong member never retires -> 'Industrial Construction Execution' (8 members, 23 Fading rows, 5/8 misfiled). Board effect: 1 G3 fail + 5 G2 rows.")

open(OUT + "rules_replay.txt", "w").write("\n".join(lines) + "\n")
json.dump({"A_set": A_set, "B_set": B_set, "C_fail": C_fail}, open(OUT + "rules_replay.json", "w"), indent=1, default=str)
