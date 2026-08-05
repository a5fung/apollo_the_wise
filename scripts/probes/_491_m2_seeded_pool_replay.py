#!/usr/bin/env python3
"""#491 M2 replay — what would the seeded assignment-pool exemption have done? ($0)

Replays _seeded_pool_admissions night-by-night over the frozen #368 exports
(scripts/probes/_368_boards.tsv, _368_rs.tsv — prod mi_themes + RS history frozen
2026-08-04) plus the LIVE Lane-2 rows captured read-only from prod on 2026-08-05
(inlined below, verbatim — mi_theme_candidates_shadow WHERE source='narrative_cogap').

Faithful to the built mechanism:
- seeded(D) = tickers in LIVE narrative_cogap rows, run_date in [D-10 trading
  sessions, D) — prior sessions only, exactly get_seeded_assignment_tickers' window.
  Backfill rows ('narrative_cogap_backfill') are EXCLUDED — the accessor excludes
  them by construction (hindsight population). Reactivation seeds: ZERO rows exist
  in prod (detector shipped 2026-08-05); the #534 replay's one incident (E-DEF
  08-04) is handled in the report, not here.
- covered(D) = latest-per-name non-Retired board rows with theme_date in [D-7d, D)
  — the get_active_themes(stale_after_days=7) idiom at run time (tonight's save
  hasn't happened yet).
- already-pool(D) ≈ RS(D-latest) >= ASSIGN_POOL_RS_FLOOR (70). Approximation stated
  in the report: the 600-fetch ceiling is ignored (517 liquid RS>=70 names measured
  08-05, so floor-clearers are inside the ceiling in practice). Before 08-05 the
  floor was 90/ceiling 200 — the replay uses TODAY'S constants deliberately: the
  question is what M2 adds ON TOP of the #534-widened pool it ships with.
- revalidated_out / same-run state: not replayable from the exports (stated).

Usage: python3 scripts/probes/_491_m2_seeded_pool_replay.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
FLOOR = 70.0
WINDOW_TRADING_DAYS = 10  # LANE2_WINDOW_TRADING_DAYS
BOARD_LOOKBACK_DAYS = 7   # get_active_themes(stale_after_days=7)

COHORT = {"RIOT", "CLSK", "APLD", "HUT", "CORZ", "CIFR", "IREN", "MARA", "WULF", "BTDR"}

# LIVE narrative_cogap rows — prod capture 2026-08-05 (scratchpad 491m2/lane2_rows.tsv).
LANE2_LIVE = [
    (date(2026, 6, 25), "AI memory and infrastructure demand surge", ["MU", "SNX"]),
    (date(2026, 7, 20), "Bitcoin miners pivoting to AI data centers", ["HUT", "IREN"]),
    (date(2026, 7, 30), "AI & Data Center Semiconductor Surge", ["LRCX", "SIMO", "ARM"]),
    (date(2026, 7, 30), "AI-Driven Power & Grid Infrastructure Boom", ["EME", "PWR"]),
    (date(2026, 7, 31), "AI data center infrastructure buildout", ["BLZE", "FLNC", "MPWR"]),
    (date(2026, 7, 31), "Semiconductor test recovery AI-driven demand", ["COHU", "MPWR"]),
    (date(2026, 8, 4), "AI Data Center Infrastructure Buildout", ["BTDR", "AMRC", "BLZE"]),
    (date(2026, 8, 4), "Semiconductor Equipment Cycle Recovery", ["AEIS", "ZBRA"]),
    (date(2026, 8, 4), "U.S. Government/Defense Spending Surge", ["PLTR", "TSAT", "VOYG", "AMRC"]),
]

AI_FRAME_TOKENS = ("ai ", "ai-", "gpu", "data center", "datacenter", "compute", "cloud")

# Four seeded names are outside the frozen RS export's universe; resolved read-only
# from prod mi_stock_scores 2026-08-05 so "already pool-eligible" is decided on real
# data, not treated as unknown. ZBRA (99.1) is the one that flips: pool-eligible on
# its own merit, NOT an M2 admission.
RS_SUPPLEMENT = {
    "SNX": {date(2026, 6, 26): 69.3, date(2026, 7, 2): 47.9, date(2026, 7, 10): 47.5},
    "EME": {date(2026, 7, 31): 42.2, date(2026, 8, 4): 45.5},
    "AEIS": {date(2026, 8, 4): 68.7},
    "ZBRA": {date(2026, 8, 4): 99.1},
}


def load_rs():
    rs = defaultdict(dict)  # date -> ticker -> rs
    with open(HERE / "_368_rs.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            d = date.fromisoformat(row["score_date"])
            rs[d][row["ticker"]] = float(row["rs"])
    return rs


def load_boards():
    boards = defaultdict(list)  # date -> [(name, stage, tickers)]
    with open(HERE / "_368_boards.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            d = date.fromisoformat(row["theme_date"])
            tks = [t for t in row["tickers"].split(",") if t]
            boards[d].append((row["name"], row["stage"], tks))
    return boards


def covered_at(boards, run_d):
    """Latest-per-name non-Retired rows, theme_date in [run_d-7d, run_d)."""
    latest = {}
    for d in sorted(boards):
        if run_d - timedelta(days=BOARD_LOOKBACK_DAYS) <= d < run_d:
            for name, stage, tks in boards[d]:
                latest[name] = (d, stage, tks)
    cov, live_themes = set(), []
    for name, (d, stage, tks) in latest.items():
        if stage != "Retired":
            cov.update(tks)
            live_themes.append((name, stage, d, tks))
    return cov, live_themes


def latest_rs(rs, run_d, tk):
    for d in sorted(rs, reverse=True):
        if d <= run_d and tk in rs[d]:
            return rs[d][tk], d
    supp = RS_SUPPLEMENT.get(tk, {})
    for d in sorted(supp, reverse=True):
        if d <= run_d:
            return supp[d], d
    return None, None


def main():
    rs, boards = load_rs(), load_boards()
    sessions = sorted(rs)  # the data spine = the trading calendar
    # replay D over sessions after the first live lane row, plus 08-05 (boards run to 08-04)
    replay_days = [d for d in sessions if d >= date(2026, 6, 26)] + [date(2026, 8, 5)]

    total_adm, nights_with = 0, 0
    print(f"{'night':<12}{'admitted (RS, trigger date)':<66}under-floor?")
    for D in replay_days:
        prior = [s for s in sessions if s < D]
        wstart = prior[-WINDOW_TRADING_DAYS] if len(prior) >= WINDOW_TRADING_DAYS else prior[0]
        seeded = {}
        for rd, name, tks in LANE2_LIVE:
            if wstart <= rd < D:
                for tk in tks:
                    seeded.setdefault(tk, (rd, name))
        if not seeded:
            continue
        cov, live_themes = covered_at(boards, D)
        admitted = []
        for tk in sorted(seeded):
            if tk in cov:
                continue
            r, rd_seen = latest_rs(rs, D, tk)
            if r is not None and r >= FLOOR:
                continue  # already pool-eligible (floor approximation)
            admitted.append((tk, r, seeded[tk][0]))
        if admitted:
            nights_with += 1
            total_adm += len(admitted)
            desc = "  ".join(f"{tk}({'?' if r is None else f'{r:.0f}'},{trg.strftime('%m-%d')})"
                             for tk, r, trg in admitted)
            print(f"{D.isoformat():<12}{desc:<66}"
                  f"{sum(1 for _, r, _ in admitted if r is not None and r < FLOOR)}/{len(admitted)}")
            for tk, r, trg in admitted:
                if tk in COHORT:
                    zones = [f"{n} [{st}]" for n, st, _, _ in live_themes
                             if any(t in n.lower() for t in AI_FRAME_TOKENS)]
                    print(f"  ↳ COHORT {tk}: live AI-frame landing zone(s): "
                          f"{'; '.join(zones) if zones else 'NONE on the board'}")
    n_nights = len(replay_days)
    print(f"\n{total_adm} admissions over {n_nights} replay nights "
          f"({nights_with} nights with any; max bound ~15/night)")


if __name__ == "__main__":
    main()
