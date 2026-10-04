"""#655 — part 2: Rule A simulated night by night over the last 18 boards (history), Rule B's recovery
cost refined, and the growth paths of the three real themes Rule C would have blocked.
Caveat (stated once): every night is read on the ONE captured excess window (60 sessions ending
10-01); for 09-08 the shared sessions are 42/60, for 09-29 58/60. Per-night p95 comes from a full
board run that night (RNG stream per board), as the engine's pass would do."""
import pickle, sys, collections, json
from datetime import date
import numpy as np
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence import theme_correctness as tc

K_A = 3
SCRATCH = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/"
OUT = SCRATCH + "655_study/"
d = pickle.load(open(SCRATCH + "655_capture.pkl", "rb"))
themes, meta, scores, sector, excess, history = d["themes"], d["board_meta"], d["scores"], d["sector"], d["excess"], d["history"]
meta_by = {m["name"]: m for m in meta}
usable = tc.usable_set(excess)
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); lines.append(s)

by_date = collections.defaultdict(list); hist = collections.defaultdict(dict)
for r in history:
    by_date[r["theme_date"]].append(r); hist[r["name"]][r["theme_date"]] = r
all_dates = sorted(by_date)
sim_dates = [x for x in all_dates if x >= date(2026, 9, 8)]
def board_at(dt):
    return [{"name": r["name"], "stage": r["stage"], "tickers": list(r["tickers"] or [])}
            for r in by_date[dt] if r["stage"] != "Retired"]

# ── Rule A night-by-night ───────────────────────────────────────────────────────────────────────
P(f"################ RULE A simulated nightly {sim_dates[0]}..{sim_dates[-1]} ({len(sim_dates)} boards)")
verdict = {}   # (name, date) -> True/False/None
for dt in sim_dates:
    b = board_at(dt)
    g3 = tc.compute_g3(b, excess, usable, scores, sector)
    for r in g3["themes"]:
        verdict[(r["name"], dt)] = r["pass_g3"]
    P(f"  {dt}: board {len(b)} G3 {g3['pass']}/{g3['n_judgeable']} = {g3['rate_pct']}%  fails {len(g3['fail_list'])}")

# streaks: consecutive judged FAIL nights (None = unjudgeable breaks nothing but does not count)
retire_events = []   # (name, date retired, streak start)
alive_sets = {}
retired_names: dict[str, date] = {}
streak = collections.defaultdict(int)
for dt in sim_dates:
    for t in board_at(dt):
        n = t["name"]
        if n in retired_names:   # under Rule A this theme no longer exists; a re-birth would be a new name/tombstone
            continue
        v = verdict.get((n, dt))
        if v is False:
            streak[n] += 1
            if streak[n] >= K_A:
                retire_events.append((n, dt, len(t["tickers"]), t["stage"]))
                retired_names[n] = dt
        elif v is True:
            streak[n] = 0
P(f"\n  Rule A (K={K_A}) retire events over the window: {len(retire_events)}")
for n, dt, sz, st in retire_events:
    rows = hist[n]; ds = sorted(rows)
    later = [x for x in ds if x > dt]
    maxsz_later = max((len(rows[x]["tickers"] or []) for x in later), default=0)
    on_board = n in meta_by
    now = next((r for r in d["report"]["g3"]["themes"] if r["name"] == n), None)
    passes_now = now["pass_g3"] if now else None
    P(f"    {dt} retire {n[:58]:58s} sz={sz} {st[:2]} | later max size={maxsz_later} on board now={on_board} passes G3 now={passes_now} rs_avg now={meta_by.get(n,{}).get('rs_avg')}")
# cost: retired themes that later became real on the tape (pass G3 now with >= 4 members)
cost = [e for e in retire_events if e[0] in meta_by and next(r for r in d["report"]["g3"]["themes"] if r["name"] == e[0])["pass_g3"]]
P(f"  retired-by-A themes that are on the board today AND pass G3 today (false kills): {len(cost)} -> {[e[0] for e in cost]}")
# what the 10-02 board would look like if Rule A had been running since 09-08
boardA = [t for t in themes if t["name"] not in retired_names]
rep = tc.build_correctness_report(boardA, excess, scores, sector)
P(f"  10-02 board had Rule A run since 09-08: removes {len(themes)-len(boardA)} -> G1 {rep['g1']['rate_pct']}% G2 {rep['g2']['rate_pct']}% "
  f"G3 {rep['g3']['pass']}/{rep['g3']['n_judgeable']}={rep['g3']['rate_pct']}% {'PASS' if rep['g3']['pass_bar'] else 'FAIL'} | "
  f"G4 {rep['g4']['small']}/{rep['g4']['n_board']}={rep['g4']['rate_pct']}% {'PASS' if rep['g4']['pass_bar'] else 'FAIL'}")
# nightly G4 and G3 after A for the last 3 nights (what the nightly check would have printed)
for dt in sim_dates[-3:]:
    b = [t for t in board_at(dt) if t["name"] not in retired_names or retired_names[t["name"]] >= dt]
    b = [t for t in b if not (t["name"] in retired_names and retired_names[t["name"]] < dt)]
    r = tc.build_correctness_report(b, excess, scores, sector)
    P(f"    {dt} with A: board {len(b)} G3 {r['g3']['rate_pct']}% {'PASS' if r['g3']['pass_bar'] else 'FAIL'} | G4 {r['g4']['small']}/{len(b)}={r['g4']['rate_pct']}% {'PASS' if r['g4']['pass_bar'] else 'FAIL'}")

# ── Rule B: recovery cost refined ────────────────────────────────────────────────────────────────
P("\n################ RULE B cost refined — shells that recovered: how many shell nights first, and did the SAME cohort grow?")
rec = []
for name, rows in hist.items():
    ds = sorted(rows)
    i = 0
    while i < len(ds):
        r = rows[ds[i]]
        if r["stage"] == "Fading" and 0 < len(r["tickers"] or []) < 3:
            j = i; shell = set()
            while j < len(ds) and rows[ds[j]]["stage"] == "Fading" and 0 < len(rows[ds[j]]["tickers"] or []) < 3:
                shell |= set(rows[ds[j]]["tickers"]); j += 1
            nights = j - i
            if j < len(ds) and rows[ds[j]]["stage"] != "Retired" and rows[ds[j]]["tickers"]:
                nxt = rows[ds[j]]
                ov = len(shell & set(nxt["tickers"]))
                grew3 = any(len(rows[x]["tickers"] or []) >= 3 for x in ds[j:])
                rec.append((name, ds[i], nights, nxt["stage"], len(nxt["tickers"]), ov, grew3))
            i = j
        else:
            i += 1
P(f"  recovery episodes: {len(rec)}; shell nights before recovery: {sorted(collections.Counter(e[2] for e in rec).items())}")
P(f"  recovered rows that kept >=1 shell member (same cohort): {sum(1 for e in rec if e[5] >= 1)}; kept both: {sum(1 for e in rec if e[5] >= 2)}; "
  f"later reached >=3 members: {sum(1 for e in rec if e[6])}")
P("  episodes recovering after exactly 1 shell night (what an immediate retire kills before any 2nd look):", sum(1 for e in rec if e[2] == 1))
for e in sorted(rec, key=lambda x: x[1]): P("    ", e)
# total shell-nights on boards (what B removes from G4 denominators) vs recoveries
tot_shell_nights = sum(1 for r in history if r["stage"] == "Fading" and 0 < len(r["tickers"] or []) < 3)
P(f"  total <3-member Fading rows in 60 days: {tot_shell_nights} (~{tot_shell_nights/len(all_dates):.1f} per night on the board); recoveries {len(rec)} -> "
  f"{100*len(rec)/max(1,tot_shell_nights):.1f}% of shell-nights precede a recovery")
# would the G4 bar have passed every night of the window with B?  (exact from history: G4 is a pure count)
P("\n  G4 per night, baseline vs Rule B (exact — G4 is a count):")
fails_base = fails_B = 0
for dt in sim_dates:
    b = board_at(dt); small = [t for t in b if len(t["tickers"]) < 3]
    fsmall = [t for t in small if t["stage"] == "Fading"]
    g4b = 100*len(small)/len(b); g4B = 100*(len(small)-len(fsmall))/(len(b)-len(fsmall))
    fails_base += g4b > 10; fails_B += g4B > 10
    P(f"    {dt}: base {len(small)}/{len(b)}={g4b:.1f}% {'FAIL' if g4b>10 else 'pass'} | B {len(small)-len(fsmall)}/{len(b)-len(fsmall)}={g4B:.1f}% {'FAIL' if g4B>10 else 'pass'}")
P(f"  nights G4 fails: baseline {fails_base}/{len(sim_dates)} ; Rule B {fails_B}/{len(sim_dates)}")

# ── Rule C: growth paths of the three real themes it would have blocked ─────────────────────────
P("\n################ RULE C — growth paths of the currently-PASSING themes whose founders fail the floor")
for n in ("Post-Acute & Home-Based Healthcare Services", "Digital Advertising & Ad-Tech Monetization Platforms",
          "Precision Timing & Motion Control Component Makers"):
    rows = hist[n]; ds = sorted(rows)
    path = [(x.isoformat()[5:], len(rows[x]["tickers"] or []), rows[x]["stage"][:2], verdict.get((n, x))) for x in ds]
    P(f"  {n}: (date, size, stage, G3-verdict-that-night)")
    P("    ", path)
    # would Rule A have retired it? (streak of 3 fails while on board)
    s = 0; killed = None
    for x in ds:
        v = verdict.get((n, x))
        if v is False:
            s += 1
            if s >= K_A: killed = x; break
        elif v is True: s = 0
    P(f"    Rule A would have retired it on: {killed}")

open(OUT + "rules_replay2.txt", "w").write("\n".join(lines) + "\n")
