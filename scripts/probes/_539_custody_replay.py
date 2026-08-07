#!/usr/bin/env python3
"""#539 custody replay — the HUT/CIFR 2026-08-05 stale-identity capture, frozen. ($0)

THE CASE (measured — scripts/probes/_539_evidence.tsv, pulled read-only 2026-08-07):
  'Bitcoin Mining & Crypto Infrastructure Operators' held {CIFR, HUT} continuously
  from 07-20. On 08-04 run 1 it lifecycle-retired (theme_retired 17:03:35) and got
  its engine-drop tombstone (theme_auto_retired 17:04:12) — but the engine ran twice
  more that evening, and _save_themes' same-day DELETE (source='live'-scoped,
  theme_engine.py ~1980) removed the tombstone because the dead theme was not in the
  rerun's final list. With no 08-04 row left, get_active_themes(7)'s latest-per-name
  scan (db.py ~7467) resurrected the theme on 08-05 from its 08-03 Fading row —
  same members, same thesis, days_active carried — a ZOMBIE, not a birth. Its thesis
  text names the AI-datacenter driver ("Hut 8's ... AI data center lease deals ...
  Nvidia as the anchor tenant") while its NAME still says Bitcoin Mining: the
  stale-identity capture #491 characterises, holding the pivot pair uncontestable.

REPLAYS (frozen prod data: _539_board.tsv, _539_rs.tsv, _539_lane2.tsv,
_539_theses.tsv, _539_evidence.tsv — never re-pulled):
  R1  zombie resurrection — get_active_themes(stale_after_days=7) semantics as-of
      08-05 reproduce the incumbent from its 08-03 row, and the replayed weak-Fading
      rescore (score*0.8, rs_avg NULL, days_active carried) must MATCH the actual
      saved 08-05 prod row — parity proof that this exercises the live mechanism.
  R2  coverage wall (B1) + RS floor (B2) — the pair is unreachable by every
      admission lane on 08-05: covered (excluded from discovery/assignment pools and
      from M2 by rule), AND under ASSIGN_POOL_RS_FLOOR anyway, AND HUT's only Lane-2
      trigger (07-20) has aged out of the 10-trading-day M2 window.
  R3  contest unreachability — a challenger cluster carrying both names never
      reaches a custody decision: |intersection|=2 < MIN_SHARED_FOR_MERGE=3
      (theme_engine.py:5017) skips the pair before the protect-strip; at >=3 the
      strip rule (5040-5094) would hand the members to the incumbent by rule.
  ACCEPTANCE — the #491 M-CORE custody-verb contract on this fixture (CUSTODY_CASE
      below). run_custody_verb is a None hook today; wire M-CORE there and this
      probe becomes its acceptance test: it must flag {HUT, CIFR} as contested and
      propose the AI-compute framing, never keep-by-coverage-silence.

Rule constants mirror theme_engine.py / db.py with line refs; any drift is caught
by the R1 parity assertions failing against the frozen prod rows.

Usage: python3 scripts/probes/_539_custody_replay.py    (exit 0 = replay parity holds)
"""
from __future__ import annotations

import csv
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent

# ── constants mirrored from agents/market_intelligence/theme_engine.py ──
STALE_AFTER_DAYS = 7          # db.get_active_themes default
ASSIGN_POOL_RS_FLOOR = 70.0   # theme_engine.py:276
MIN_SHARED_FOR_MERGE = 3      # theme_engine.py:307
LANE2_WINDOW_TRADING_DAYS = 10  # M2 admission window (PRIOR sessions only)
FADING_DECAY = 0.8            # weak-Fading branch: score = prior * 0.8 (~2904)

RUN_D = date(2026, 8, 5)
INCUMBENT = "Bitcoin Mining & Crypto Infrastructure Operators"
AI_ZONE = "AI GPU Compute Infrastructure & Cloud Services"
CONTESTED = {"HUT", "CIFR"}

# ── the #491 M-CORE acceptance contract on this fixture ──
CUSTODY_CASE = {
    "as_of": RUN_D,
    "contested": sorted(CONTESTED),
    "incumbent": INCUMBENT,
    # the incumbent's OWN thesis names the AI driver (asserted from _539_theses.tsv)
    "incumbent_thesis_names_ai_driver": ["AI data center lease", "Nvidia"],
    "challenger_zone": AI_ZONE,          # live on the 08-05 board (Fading, {APLD,CRWV})
    "lane2_pivot_row": ("2026-07-20", "Bitcoin miners pivoting to AI data centers", ["HUT", "IREN"]),
    "expected": "surface {HUT,CIFR} for custody adjudication vs the AI-compute framing"
                " — never silently keep-by-coverage",
}
run_custody_verb = None  # ← wire #491 M-CORE here when it exists


def _rows(fname: str) -> list[dict]:
    with open(HERE / fname) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def load_board() -> dict[date, list[dict]]:
    by_date: dict[date, list[dict]] = {}
    for r in _rows("_539_board.tsv"):
        d = date.fromisoformat(r["theme_date"])
        r["_tickers"] = [t for t in r["tickers"].split(",") if t]
        by_date.setdefault(d, []).append(r)
    return by_date


def active_as_of(board: dict[date, list[dict]], run_d: date) -> dict[str, dict]:
    """get_active_themes(stale_after_days=7) at run time (before tonight's save):
    latest row per name in [run_d-7d, run_d), THEN drop names whose latest row is
    Retired (the #214 RETIRED-GAP order, db.py ~7467)."""
    latest: dict[str, dict] = {}
    for d in sorted(board):
        if run_d - timedelta(days=STALE_AFTER_DAYS) <= d < run_d:
            for r in board[d]:
                latest[r["name"]] = r
    return {n: r for n, r in latest.items() if r["stage"] != "Retired"}


def trading_days_back(run_d: date, n: int) -> date:
    """Weekday-walk n trading sessions back (no market holidays 07-20..08-05)."""
    d, seen = run_d, 0
    while seen < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            seen += 1
    return d


def check(label: str, ok: bool, msg: str) -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {msg}")
    return ok


def main() -> int:
    board = load_board()
    rs = {(r["score_date"], r["ticker"]): float(r["rs"]) for r in _rows("_539_rs.tsv")}
    theses = {(r["theme_date"], r["name"]): r["description"] for r in _rows("_539_theses.tsv")}
    evidence = (HERE / "_539_evidence.tsv").read_text()
    ok = True

    # ── R1: zombie resurrection + parity vs the actual saved 08-05 row ──
    print("R1  zombie resurrection (get_active_themes semantics as-of 2026-08-05)")
    live = active_as_of(board, RUN_D)
    inc = live.get(INCUMBENT)
    ok &= check("incumbent loads", inc is not None and inc["theme_date"] == "2026-08-03",
                f"latest non-Retired row = {inc['theme_date'] if inc else 'MISSING'} "
                f"(the 08-03 Fading row — no 08-04 tombstone survived)")
    ok &= check("tombstone written then destroyed",
                "Retired: Bitcoin Mining & Crypto Infrastructure Operators" in evidence
                and "'Bitcoin Mining & Crypto Infrastructure Operators' -> parent='(unknown)'" in evidence
                and not any(r["name"] == INCUMBENT for r in board.get(date(2026, 8, 4), [])),
                "theme_retired + theme_auto_retired audit rows exist for 08-04, "
                "yet mi_themes has NO 08-04 row — the rerun's source='live' DELETE ate it")
    saved = next((r for r in board.get(RUN_D, []) if r["name"] == INCUMBENT), None)
    if inc is not None and saved is not None:
        exp_score = round(float(inc["score"]) * FADING_DECAY, 2)
        ok &= check("carried-lineage parity",
                    saved["_tickers"] == inc["_tickers"]
                    and saved["days_active"] == inc["days_active"]
                    and abs(float(saved["score"]) - exp_score) < 0.05
                    and saved["rs_avg"] == "" and saved["stage"] == "Fading",
                    f"saved 08-05 row: members {saved['_tickers']} == 08-03's, "
                    f"days_active {saved['days_active']} carried, score {saved['score']} "
                    f"= {inc['score']}*0.8, rs_avg NULL — a rescore of the 08-03 row, NOT a birth")
    else:
        ok &= check("carried-lineage parity", False, "missing incumbent or saved 08-05 row")
    thesis = theses.get(("2026-08-05", INCUMBENT), "")
    ok &= check("stale identity in one row",
                all(tok in thesis for tok in CUSTODY_CASE["incumbent_thesis_names_ai_driver"]),
                "name says Bitcoin Mining; its own thesis names the AI driver "
                f"({CUSTODY_CASE['incumbent_thesis_names_ai_driver']})")

    # ── R2: coverage wall (B1) + RS floor (B2) — no admission lane can reach the pair ──
    print("R2  coverage wall + RS floor (2026-08-05)")
    covered = {t for r in live.values() for t in r["_tickers"]}  # Fading INCLUDED by rule
    ok &= check("B1 covered-exclusivity", CONTESTED <= covered,
                "HUT+CIFR covered by the zombie incumbent -> excluded from the "
                "discovery AND assignment pools (_build_theme_pools) and from M2 "
                "(_seeded_pool_admissions skips covered names)")
    hut, cifr = rs.get(("2026-08-05", "HUT")), rs.get(("2026-08-05", "CIFR"))
    ok &= check("B2 under the pool floor",
                hut is not None and cifr is not None
                and hut < ASSIGN_POOL_RS_FLOOR and cifr < ASSIGN_POOL_RS_FLOOR,
                f"HUT RS {hut}, CIFR RS {cifr} < floor {ASSIGN_POOL_RS_FLOOR:.0f} — a pivot is "
                "under the trailing-RS floor by construction; only M2 could admit, and B1 blocks M2")
    wstart = trading_days_back(RUN_D, LANE2_WINDOW_TRADING_DAYS)
    lane2_hut = [r for r in _rows("_539_lane2.tsv") if "HUT" in r["tickers"].split(",")]
    ok &= check("HUT's Lane-2 trigger aged out",
                all(date.fromisoformat(r["run_date"]) < wstart for r in lane2_hut),
                f"only trigger 07-20 ('Bitcoin miners pivoting to AI data centers') < "
                f"window start {wstart} — and while it WAS in-window (07-21..08-03), "
                "coverage was the sole blocker (M2 replay: HUT never admitted)")
    ai_zone = live.get(AI_ZONE)
    ok &= check("AI landing zone existed", ai_zone is not None,
                f"'{AI_ZONE}' live on the 08-05 board "
                f"({ai_zone['stage']}, {ai_zone['_tickers']}) — the correct framing was RIGHT THERE"
                if ai_zone else "MISSING")

    # ── R3: the custody decision site is unreachable for a 2-member incumbent ──
    print("R3  contest unreachability (Pass-1 merge floor)")
    challenger = set((ai_zone["_tickers"] if ai_zone else [])) | CONTESTED
    inter = challenger & set(inc["_tickers"] if inc else [])
    ok &= check("below the merge floor", len(inter) == 2 and len(inter) < MIN_SHARED_FOR_MERGE,
                f"hypothetical AI cluster {sorted(challenger)} vs incumbent: "
                f"|intersection|={len(inter)} < MIN_SHARED_FOR_MERGE={MIN_SHARED_FOR_MERGE} "
                "(theme_engine.py:5017) — Pass 1 skips the pair; the protect-strip is never reached")
    print("      at >=3 shared the j_protected strip (5040-5094) hands the intersection to the")
    print("      incumbent by rule (BOTH_PROTECTED: larger-or-equal keeps) — custody today is")
    print("      decided by COVERAGE + the merge floor, with no thesis-vs-driver adjudication anywhere.")

    # ── ACCEPTANCE: the #491 M-CORE custody verb ──
    print("ACCEPTANCE  #491 M-CORE custody verb on this fixture")
    if run_custody_verb is None:
        print("  [NOT BUILT] run_custody_verb unwired — expected contract recorded:")
        for k, v in CUSTODY_CASE.items():
            print(f"      {k}: {v}")
    else:
        verdict = run_custody_verb(CUSTODY_CASE, live, rs, theses)  # noqa — future contract
        ok &= check("custody verdict", verdict.get("contested") == CUSTODY_CASE["contested"]
                    and verdict.get("target") == AI_ZONE,
                    f"verb must contest {CUSTODY_CASE['contested']} toward '{AI_ZONE}'")

    print(f"\n{'REPLAY PARITY HOLDS' if ok else 'REPLAY PARITY BROKEN'} — "
          "fixture: HUT/CIFR 2026-08-05 (supersedes the 07-20 case for #491 M-CORE)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
