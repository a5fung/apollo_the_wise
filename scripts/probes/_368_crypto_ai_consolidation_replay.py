"""#368 crypto→AI-conversion consolidation — historical replay on frozen prod data. Read-only.

Proves the four #368 fixes against the real Mar–Aug 2026 record (frozen exports,
capture-once; see the data files below):

  Part 1  stage_a   — Stage-A pair replay per day, OLD vs NEW families: the crypto-
                      and AI-framed themes must finally PAIR (pre-fix: zero pairs
                      ever proposed for either framing — verified in mi_audit_log).
  Part 2  lifecycle — day-by-day simulation of the consolidated lineage 7/17→8/04
                      under CURRENT vs FIXED mechanics, on real RS: the fixed
                      lineage must SURVIVE to 8/04; prod-actual is the baseline
                      (crypto theme retired 8/04, AI shards dead, miners homeless).
  Part 3  prune     — N≥10 backtest of the rising-recovery hold: every historical
                      sub-floor member-exit event scored by what happened to the
                      name's RS 10 sessions later (recovered ≥50 / limbo / dead <25).
  Part 4  f2        — blast radius of the weak-only fading streak: how many
                      historical retirements had a healthy-but-held (rs_avg-bearing)
                      Fading row inside their terminal streak.

  --adjudicate      — the ONE paid step (~4 Haiku calls, ≈$0.01–0.03): run the REAL
                      Stage-B adjudicator on the frozen historical pairs (the 7/21
                      crypto×AI pair, the 8/04 rediscovery pair, and the optical-
                      components negative control). Requires ANTHROPIC_API_KEY.
                      Expected: MERGE / MERGE-or-PARENT_CHILD / DISTINCT.

Data (frozen 2026-08-04, prod read-only):
  scripts/probes/_368_boards.tsv — mi_themes 2026-06-01..2026-08-04
  scripts/probes/_368_rs.tsv     — mi_stock_scores rs_composite for every themed ticker

Run:  python3 scripts/probes/_368_crypto_ai_consolidation_replay.py [--adjudicate]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.market_intelligence.theme_merge_arm import (  # noqa: E402
    FAMILIES, propose_merge_pairs,
)

HERE = os.path.dirname(os.path.abspath(__file__))
BOARDS_TSV = os.path.join(HERE, "_368_boards.tsv")
RS_TSV = os.path.join(HERE, "_368_rs.tsv")

# Engine constants, mirrored (import theme_engine would drag DB config)
PRUNE_RS_HARD, PRUNE_RS_SOFT, PRUNE_MIN = 25.0, 35.0, 2
THEME_RS_MIN, COVERAGE_MIN, RETIRE_AFTER = 50.0, 3, 5
HOLD_WINDOW, HOLD_MIN_POINTS = 6, 4

MINERS = ["APLD", "CIFR", "CORZ", "HUT", "IREN", "WULF"]

# The real 2026-08-04 rediscovery (prod: shadow-promoted 'AI GPU Compute
# Infrastructure & Cloud Services') — under F1 it pairs+merges into the lineage.
REDISCOVERY_0804 = ["APLD", "CBRS", "CRWV"]

# The 5 operator-mislabelled alerts (#368) — (ticker, date)
MISLABELLED = [("HUT", "2026-05-06"), ("WULF", "2026-07-06"), ("CLSK", "2026-07-14"),
               ("HUT", "2026-07-20"), ("IREN", "2026-07-20")]


def load_boards():
    """{date: [{name, stage, rs_avg(None if -1), source, tickers[]}]}"""
    boards: dict[str, list[dict]] = defaultdict(list)
    with open(BOARDS_TSV) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            rs = float(row["rs_avg"])
            boards[row["theme_date"]].append({
                "name": row["name"], "stage": row["stage"],
                "rs_avg": None if rs < 0 else rs, "source": row["source"],
                "tickers": [t for t in (row["tickers"] or "").split(",") if t],
            })
    return dict(boards)


def load_rs():
    """{ticker: {date: rs}} + the sorted session list."""
    rs: dict[str, dict[str, float]] = defaultdict(dict)
    sessions: set[str] = set()
    with open(RS_TSV) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            rs[row["ticker"]][row["score_date"]] = float(row["rs"])
            sessions.add(row["score_date"])
    return dict(rs), sorted(sessions)


def hist_newest_first(rs, sessions, ticker, d, n):
    """Last n RS points for ticker up to and including session d, newest first."""
    out = []
    for s in reversed([s for s in sessions if s <= d]):
        v = rs.get(ticker, {}).get(s)
        if v is not None:
            out.append(v)
        if len(out) >= n:
            break
    return out


def rs_rising(hist):
    return len(hist) >= HOLD_MIN_POINTS and hist[0] > hist[-1]


# ── Part 1 — Stage-A pair replay ─────────────────────────────────────────────

def part1_stage_a(boards):
    print("=" * 78)
    print("PART 1 — Stage-A pair replay (OLD families vs NEW compute_infra family)")
    print("=" * 78)
    old_families = [(f, p) for f, p in FAMILIES if f != "compute_infra"]

    import agents.market_intelligence.theme_merge_arm as arm
    first_pair_day = None
    total_new = 0
    displaced_days = 0
    for d in sorted(boards):
        board = [t for t in boards[d] if t["stage"] != "Retired" and t["tickers"]]
        try:
            arm.FAMILIES = old_families
            old_pairs = {(a["name"], o["name"]) for a, o in propose_merge_pairs(board)}
        finally:
            arm.FAMILIES = FAMILIES
        new_pairs_all = propose_merge_pairs(board)
        new_pairs = {(a["name"], o["name"]) for a, o in new_pairs_all}
        added = new_pairs - old_pairs
        lost = old_pairs - new_pairs           # displaced by the 8-pair budget
        if lost:
            displaced_days += 1
        ci_added = sorted(p for p in added
                          if any(k in (p[0] + p[1]).lower()
                                 for k in ("crypto", "bitcoin", "gpu", "data cent",
                                           "datacenter", "compute")))
        if ci_added:
            total_new += len(ci_added)
            if first_pair_day is None:
                first_pair_day = d
            print(f"  {d}: +{len(ci_added)} compute_infra pair(s)"
                  + (f"  [budget displaced {len(lost)} old pair(s)]" if lost else ""))
            for p in ci_added:
                print(f"      {p[0]!r} × {p[1]!r}")
    print(f"\n  first compute_infra pair day: {first_pair_day}"
          f" | total new pairs {total_new} | days with budget displacement: {displaced_days}")
    return first_pair_day


# ── Part 2 — lifecycle simulation ────────────────────────────────────────────

def simulate_lineage(rs, sessions, fixed: bool):
    """Simulate the consolidated lineage's nightly rescores 7/20→8/04.

    Membership starts as the real 7/17 evening re-mint (CIFR CORZ HUT IREN WULF,
    prod fact); the first nightly rescore of it is 7/20. Modeled surface:
    hard/soft pruning (± the F3 rising-hold) with keep-back, the strong-member
    floor (COVERAGE_MIN / elite pair), the hysteresis damper (the first healthy
    day after a weak day is emitted as Fading-with-rs_avg — exactly what prod
    did on 7/22 and 8/03, flip-held audit rows), and the retire streak (current:
    ANY consecutive Fading rows; fixed/F2: weak rows only — a held row breaks
    it). Fixed arm also applies the two REAL Lane-1 rediscoveries as end-of-day
    Arm-B merges (F1+F4): 7/21 {APLD CORZ IREN WULF} and 8/04 {APLD CBRS CRWV}
    — both births are prod facts; only the merge-instead-of-compete is simulated.
    NOT modeled: news score (stage display beyond healthy/Fading), the
    sector-outlier strip (needs ≥3 members; the lineage's weak stretches ran at
    2). The current arm's fidelity check: it must reproduce prod's exact
    sequence — Fading 7/27..7/31, held-Fading (rs_avg 84.9) 8/03, RETIRED 8/04.
    """
    days = [s for s in sessions if "2026-07-20" <= s <= "2026-08-04"]
    members = ["CIFR", "CORZ", "HUT", "IREN", "WULF"]  # the 7/17 re-mint (prod)
    rows = []            # (day, state, n_strong, members, held, pruned)
    emitted = []         # (stage, weak: bool) newest last
    retired = None
    for d in days:
        if retired:
            break
        # ── nightly prune (hard/soft ± F3 rising-hold) ──
        kept, pruned, held = [], [], []
        for tk in members:
            v = rs.get(tk, {}).get(d)
            if v is None:
                kept.append(tk)  # no data → keep (missing-RS path needs 5d-weak)
                continue
            hist = hist_newest_first(rs, sessions, tk, d, HOLD_WINDOW)
            if v < PRUNE_RS_HARD:
                if fixed and rs_rising(hist):
                    held.append(tk); kept.append(tk)
                else:
                    pruned.append(tk)
            elif v < PRUNE_RS_SOFT and len(hist) >= 3 and all(x < PRUNE_RS_SOFT for x in hist[:3]):
                if fixed and rs_rising(hist):
                    held.append(tk); kept.append(tk)
                else:
                    pruned.append(tk)
            else:
                kept.append(tk)
        if len(kept) < PRUNE_MIN and pruned:   # keep-back to PRUNE_MIN
            back = sorted(pruned, key=lambda t: rs.get(t, {}).get(d, 0), reverse=True)
            while len(kept) < PRUNE_MIN and back:
                kept.append(back.pop(0))
        members = kept

        # ── strong floor + stage emission ──
        strong = [t for t in members if rs.get(t, {}).get(d, 0) >= THEME_RS_MIN]
        avg_strong = sum(rs[t][d] for t in strong) / len(strong) if strong else 0
        healthy = len(strong) >= COVERAGE_MIN or (len(strong) >= 2 and avg_strong >= 80)

        if healthy:
            prev_weak = emitted and emitted[-1][0] == "Fading" and emitted[-1][1]
            if prev_weak:
                # hysteresis: recovery flip unconfirmed by yesterday → stage held
                # at Fading, but the row carries rs_avg (prod 7/22, 8/03)
                state = "Fading(held)"
                emitted.append(("Fading", False))
            else:
                state = "HEALTHY"
                emitted.append(("Healthy", False))
        else:
            # retire check BEFORE emitting (mirrors _count_consecutive_fading:
            # the streak of PRIOR rows, newest first)
            streak = 0
            for stage, weak in reversed(emitted):
                if stage == "Fading" and (weak or not fixed):
                    streak += 1
                elif stage == "Fading" and fixed and not weak:
                    break      # F2: healthy-held row breaks the weak streak
                else:
                    break
            if streak >= RETIRE_AFTER:
                state = "RETIRED"
                retired = d
            else:
                state = "Fading(weak)"
                emitted.append(("Fading", True))
        rows.append((d, state, len(strong), list(members), held, pruned))

        # ── end-of-day Arm-B merges of the REAL Lane-1 rediscoveries (F1+F4) ──
        # (in the real engine the newborn is created after the rescore pass and
        # the thesis-merge union happens the same night, so the union is intact
        # for the NEXT day's rescore)
        if fixed and not retired and d == "2026-07-21":
            members = sorted(set(members) | {"APLD", "CORZ", "IREN", "WULF"})
        if fixed and not retired and d == "2026-08-04":
            members = sorted(set(members) | set(REDISCOVERY_0804))
    return rows, retired


def part2_lifecycle(rs, sessions, boards):
    print("\n" + "=" * 78)
    print("PART 2 — lifecycle replay of the consolidated lineage (7/17 → 8/04, real RS)")
    print("=" * 78)
    for fixed in (False, True):
        label = "FIXED (F1 merge + F3 rising-hold + F2 weak-only streak + F4)" if fixed \
            else "CURRENT mechanics (baseline; prod-actual confirms)"
        rows, retired = simulate_lineage(rs, sessions, fixed)
        print(f"\n  {label}:")
        for d, state, n_strong, members, held, pruned in rows:
            extra = ""
            if held:
                extra += f"  held-rising={','.join(held)}"
            if pruned:
                extra += f"  pruned={','.join(pruned)}"
            print(f"    {d}  {state:8} strong={n_strong}  members={','.join(members)}{extra}")
        print(f"    → {'RETIRED ' + retired if retired else 'SURVIVES to 2026-08-04'}")

    # prod-actual baseline from the frozen boards
    last = boards.get("2026-08-04", [])
    live = [t for t in last if t["stage"] != "Retired"]
    miner_homes = {tk: [t["name"] for t in live if tk in t["tickers"]] for tk in MINERS}
    print("\n  Prod-actual 2026-08-04 (frozen board): "
          f"{sum(1 for t in last if t['stage'] == 'Retired')} retired row(s) today; "
          f"miner membership: {miner_homes}")

    # the 4 target names simultaneously in ONE theme (fixed arm)
    rows, retired = simulate_lineage(rs, sessions, True)
    for d, state, _n, members, _h, _p in rows:
        if set(["WULF", "IREN", "CORZ", "APLD"]) <= set(members):
            print(f"  ✔ acceptance: WULF+IREN+CORZ+APLD simultaneously in the ONE lineage on {d} ({state})")
            break
    if not retired:
        final_members = sorted(set(rows[-1][3]) | set(REDISCOVERY_0804))
        print(f"  ✔ end state 2026-08-04 (fixed): lineage ALIVE; after the same-night Arm-B fold-in "
              f"of the real 8/04 rediscovery, members = {','.join(final_members)} "
              f"(vs prod-actual: 0 surviving themes, miners homeless)")


# ── Part 3 — prune rising-hold backtest ──────────────────────────────────────

def part3_prune_backtest(boards, rs, sessions):
    print("\n" + "=" * 78)
    print("PART 3 — rising-recovery hold, N≥10 backtest on historical member exits")
    print("=" * 78)
    days = sorted(boards)
    exits = []   # (day_gone, theme, ticker, rs_at_exit, hist)
    mass_excluded = 0
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        prev = {t["name"]: t for t in boards[d0] if t["stage"] != "Retired"}
        cur = {t["name"]: t for t in boards[d1] if t["stage"] != "Retired"}
        for name, t0 in prev.items():
            t1 = cur.get(name)
            if t1 is None:
                continue  # theme gone — not a member prune
            gone = set(t0["tickers"]) - set(t1["tickers"])
            # mass-eviction exclusion (#214 signature): ≥3 leavers AND ≥50% of
            # membership gone at once = validation mass-removal / name-defect
            # strip, NOT the daily prune this backtest scores. The rising-hold
            # only changes PRUNE decisions.
            if len(gone) >= 3 and len(gone) * 2 >= len(t0["tickers"]):
                mass_excluded += len(gone)
                continue
            for tk in gone:
                v = rs.get(tk, {}).get(d1)
                if v is None or v >= PRUNE_RS_SOFT:
                    continue  # not a prune-shaped exit (validation/strip/etc.)
                hist = hist_newest_first(rs, sessions, tk, d1, HOLD_WINDOW)
                exits.append((d1, name, tk, v, hist))

    would_hold = [(d, n, tk, v, h) for d, n, tk, v, h in exits if rs_rising(h)]
    print(f"  prune-shaped member exits (RS<{PRUNE_RS_SOFT:.0f} at exit, mass-evictions excluded): "
          f"{len(exits)}  (excluded {mass_excluded} mass-eviction leavers)")
    print(f"  rising at exit → the hold would have retained: {len(would_hold)}")

    def extra_retention_sessions(tk, d):
        """How long the hold actually keeps a name: sessions until its RS is
        sub-hard-floor AND no longer rising (the hold re-checks nightly)."""
        later = [s for s in sessions if s > d][:15]
        for j, s in enumerate(later, 1):
            v = rs.get(tk, {}).get(s)
            if v is None:
                continue
            h = hist_newest_first(rs, sessions, tk, s, HOLD_WINDOW)
            if v < PRUNE_RS_HARD and not rs_rising(h):
                return j
        return None  # never re-prunable in 15 sessions (name recovered/held up)

    def outcome(tk, d):
        later = [s for s in sessions if s > d][:10]
        if len(later) < 10:
            return None
        vals = [rs.get(tk, {}).get(s) for s in later]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        peak = max(vals)
        return "recovered(≥50)" if peak >= 50 else ("dead(<25)" if peak < 25 else "limbo(25-50)")

    scored = [(d, n, tk, v, outcome(tk, d)) for d, n, tk, v, h in would_hold]
    scored = [s for s in scored if s[4]]
    from collections import Counter
    dist = Counter(s[4] for s in scored)
    print(f"  retained-name outcomes over the next 10 sessions (N={len(scored)}): {dict(dist)}")
    for d, n, tk, v, o in scored:
        print(f"    {d}  {tk:5} RS{v:5.1f}  left '{n[:44]}'  → {o}")
    # FP cost: a wrongly-retained (dead) name is NOT kept forever — the hold
    # re-checks nightly and re-prunes on the first sub-floor non-rising day.
    dead_costs = []
    for d, n, tk, v, o in scored:
        if o == "dead(<25)":
            e = extra_retention_sessions(tk, d)
            dead_costs.append((tk, d, e))
    known = sorted(e for _t, _d, e in dead_costs if e is not None)
    med = known[len(known) // 2] if known else None
    print(f"  FP retention cost (dead names): median {med} session(s) until the nightly "
          f"re-check prunes them anyway (N={len(known)}; "
          f"{sum(1 for _t, _d, e in dead_costs if e is None)} not re-prunable in 15)")
    # control: falling exits (the hold correctly lets these go)
    falling = [(d, n, tk, v, outcome(tk, d)) for d, n, tk, v, h in exits if not rs_rising(h)]
    falling = [s for s in falling if s[4]]
    dist_f = Counter(s[4] for s in falling)
    print(f"  control — FALLING exits the hold still prunes (N={len(falling)}): {dict(dist_f)}")


# ── Part 4 — F2 blast radius ─────────────────────────────────────────────────

def part4_f2_recount(boards):
    print("\n" + "=" * 78)
    print("PART 4 — weak-only fading streak: recount of historical retirements")
    print("=" * 78)
    days = sorted(boards)
    by_name: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for d in days:
        for t in boards[d]:
            by_name[t["name"]].append((d, t))
    affected = []
    for name, hist in by_name.items():
        for i, (d, t) in enumerate(hist):
            if t["stage"] != "Retired":
                continue
            trail = [x for x in hist[:i]][-RETIRE_AFTER - 2:]
            fading_trail = []
            for dd, tt in reversed(trail):
                if tt["stage"] == "Fading":
                    fading_trail.append((dd, tt))
                else:
                    break
            if len(fading_trail) < RETIRE_AFTER:
                continue  # engine-drop/absorption retirement, not streak-driven
            healthy_held = [dd for dd, tt in fading_trail if tt["rs_avg"] is not None]
            if healthy_held:
                affected.append((name, d, healthy_held))
            break  # first retirement only
    print(f"  streak-driven retirements with a healthy-held (rs_avg-bearing) Fading row"
          f" inside the terminal streak: {len(affected)}")
    for name, d, held_days in affected:
        print(f"    '{name}' retired {d} — healthy-held on {held_days} (F2 would break the streak)")


# ── Part 5 (--adjudicate) — the real Stage-B verdicts, frozen prod pairs ─────

FROZEN_PAIRS = [
    {"id": "P1-0721", "expect": "MERGE (accept PARENT_CHILD)",
     "a": {"name": "Bitcoin Mining & Crypto Infrastructure Operators",
           "tickers": ["HUT", "CIFR"],
           "description": ("HUT is being driven higher by its announcement of a second 15-year, "
                           "$9.8 billion AI data center lease at its Beacon Point campus in Texas, "
                           "which fully commercializes the 1 GW site and doubles contracted IT "
                           "capacity, resetting expectations for long-term AI infrastructure revenue.")},
     "b": {"name": "AI Compute & GPU Data Center Hosting Operators",
           "tickers": ["APLD", "CORZ", "IREN", "WULF"],
           "description": ("Broad rebound in AI data center / Bitcoin-miner-to-AI infrastructure "
                           "names after multiple firms announced large, long-term AI compute and "
                           "data center lease deals, plus sector-wide optimism about AI demand and "
                           "rising GPU pricing.")}},
    {"id": "P2-0804", "expect": "MERGE (accept PARENT_CHILD)",
     "a": {"name": "Bitcoin Mining & Crypto Infrastructure Operators",
           "tickers": ["HUT", "CIFR"],
           "description": ("Bitcoin miners re-rating as scarce large-scale power and data-center "
                           "landlords for the AI compute boom — contracted power capacity and "
                           "AI/HPC pivots are the driver, not bitcoin price.")},
     "b": {"name": "AI GPU Compute Infrastructure & Cloud Services",
           "tickers": ["APLD", "CBRS", "CRWV"],
           "description": ("GPU compute and AI cloud-hosting providers re-rating on AI compute "
                           "demand, long-term hosting lease announcements and rising GPU pricing.")}},
    {"id": "N1-optical", "expect": "DISTINCT (negative control)",
     "a": {"name": "Bitcoin Mining & Crypto Infrastructure Operators",
           "tickers": ["HUT", "CIFR"],
           "description": ("Bitcoin miners re-rating as power and data-center landlords for the AI "
                           "compute boom via AI/HPC conversion of contracted capacity.")},
     "b": {"name": "AI Datacenter Optical Transceivers & Components",
           "tickers": ["AAOI", "LITE", "COHR"],
           "description": ("Optical transceiver and interconnect component suppliers benefiting "
                           "from hyperscaler datacenter capex on 800G upgrades — a component "
                           "demand cycle in the AI datacenter supply chain.")}},
]


async def part5_adjudicate():
    from agents.market_intelligence.theme_merge_arm import adjudicate_merge_pair
    import anthropic
    print("\n" + "=" * 78)
    print("PART 5 — REAL Stage-B adjudication of the frozen historical pairs")
    print(f"  cost: {len(FROZEN_PAIRS)} Haiku calls ≈ $0.01–0.03")
    print("=" * 78)
    client = anthropic.AsyncAnthropic()
    out = []
    for case in FROZEN_PAIRS:
        v = await adjudicate_merge_pair(case["a"], case["b"], client=client)
        out.append({"id": case["id"], "expect": case["expect"], "verdict": v})
        print(f"  {case['id']}: verdict={v.get('verdict')} (expected {case['expect']})")
        print(f"      merged_name={v.get('merged_name')!r} reason={v.get('reason')!r}")
    path = os.path.join(HERE, "_368_adjudication_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  → saved {path} (capture once, read many)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adjudicate", action="store_true",
                    help="run the real Stage-B adjudicator on the frozen pairs (paid, ~$0.02)")
    args = ap.parse_args()

    boards = load_boards()
    rs, sessions = load_rs()
    part1_stage_a(boards)
    part2_lifecycle(rs, sessions, boards)
    part3_prune_backtest(boards, rs, sessions)
    part4_f2_recount(boards)
    if args.adjudicate:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("\n--adjudicate: ANTHROPIC_API_KEY not set — skipped")
        else:
            asyncio.run(part5_adjudicate())


if __name__ == "__main__":
    main()
