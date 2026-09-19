"""#454 R3 part (2) — regime-stratified re-cut of the #268b calibration envelope.

ANALYSIS ONLY — read-only prod SELECTs, output to stdout; changes NOTHING live.
Companion doc: docs/analysis/454_regime_stratified_envelope_2026-07-17.md.

THE ASK (premortem R3, docs/analysis/premortem_450_2026-07-11.md): the kill/scale
envelope (`kill_scale_bands.CALIBRATION_ENVELOPE`, #268b Phase B, n=399) was cut on ONE
mixed-regime 12-month window with no regime stratification — re-cut it per regime and see
whether the mixed window materially misprices any regime.

WHAT THIS SCRIPT DOES:
  Stage 1 — ATTEMPT the exact re-cut: locate the per-trade R series the envelope was
      built from (simulated outcomes of the judge-HIGH cohort, 2025-06-09..2026-05-04)
      joined to `mi_market_regime`. If the series is unreachable read-only from prod,
      print EXACTLY what is missing and fall through.
  Stage 2 — REACHABLE analysis: stratify what survives — the regime-day composition of
      the calibration window (the SAME `mi_market_regime` history the replay's grade
      stage consumed), the non-Bull cluster, and a pro-rata estimate of per-regime
      candidate/trade exposure using the preserved monthly candidate table from
      `docs/analysis/selection_replay_268_phaseB.md` (the only surviving per-month
      population record).

PROVENANCE OF THE ENVELOPE (how #268b was built — the trail this script chases):
  `scripts/selection_replay_268.py --simulate` wrote per-trade R to a CSV
  (default /tmp inside the container, never a DB table) → `scripts/_killscale_bands_268.py`
  joined `replay268_phaseB.csv` × `replay268_tiers.csv` (a tier dump) and printed the
  envelope stats that were then signed into `docs/setups/safeguards.md` + hardcoded as
  `CALIBRATION_ENVELOPE`.

Usage (from the repo root, workstation with prod SSH access):
    python scripts/_454_regime_stratified_envelope.py [--ssh apollo@87.99.134.162]

READ-ONLY GUARANTEE: every query is asserted to start with SELECT; the ssh path runs
`psql -tAX -c "<SELECT …>"` only. No writes, no DDL, no temp tables.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# The SSoT envelope constant (kill_scale_bands.py is dependency-free at import time).
from agents.market_intelligence.kill_scale_bands import (  # noqa: E402
    CALIBRATION_ENVELOPE, _SAMPLE_FLOOR,
)

WINDOW_FROM, WINDOW_TO = "2025-06-09", "2026-05-04"   # Phase B (analysis doc header)

# Preserved population record — docs/analysis/selection_replay_268_phaseB.md
# "Monthly tier distribution" table (candidates per month). The per-DAY counts are
# unrecoverable (rows deleted, see Stage 1), so month is the finest surviving grain.
MONTHLY_CANDIDATES = {
    "2025-06": 57, "2025-07": 124, "2025-08": 180, "2025-09": 97, "2025-10": 167,
    "2025-11": 136, "2025-12": 77, "2026-01": 104, "2026-02": 139, "2026-03": 95,
    "2026-04": 117, "2026-05": 14,
}
PHASEB_TOTALS = {"candidates": 1307, "simulated": 953, "judge_high_simulated": 399}


def make_runner(ssh_host: str):
    """SELECT-only query runner over `ssh <host> docker exec … psql -tAX`. Returns
    rows as lists of '|'-split strings (psql -A default separator)."""
    def run(sql: str) -> list[list[str]]:
        s = " ".join(sql.split())
        assert s.upper().startswith("SELECT"), "read-only: SELECTs only"
        assert not any(ch in s for ch in '"\\$`'), "unsupported char for ssh quoting"
        remote = (f'docker exec -i apollo-postgres psql -U apollo -d apollo -tAX -c "{s}"')
        out = subprocess.run(["ssh", "-o", "ConnectTimeout=15", ssh_host, remote],
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(f"psql failed: {out.stderr.strip()[:500]}")
        return [ln.split("|") for ln in out.stdout.splitlines() if ln.strip()]
    return run


def stage1_attempt_exact_recut(run) -> bool:
    """Chase the per-trade R series. Returns True only if an exact per-regime re-cut is
    possible read-only from prod (spoiler as of 2026-07-17: it is not — prints why)."""
    print("## Stage 1 — attempt the exact per-trade re-cut\n")
    missing: list[str] = []

    # (a) Were simulated outcomes ever persisted to the DB? (No R/outcome columns on
    # mi_ep_alerts; stage_simulate wrote CSV only — verify, don't assume.)
    cols = [r[0] for r in run(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='mi_ep_alerts'")]
    outcome_cols = [c for c in cols if any(k in c.lower() for k in
                    ("r_multiple", "pnl", "risk", "outcome", "exit"))]
    if not outcome_cols:
        missing.append(
            "Per-trade simulated outcomes: NEVER DB-persisted — "
            "`selection_replay_268.py --simulate` wrote r_multiple to a CSV only "
            "(default /tmp inside the container; containers rebuilt many times since "
            "the 2026-06-11/12 run). `mi_ep_alerts` has no outcome column.")
    else:
        print(f"  candidate outcome columns found on mi_ep_alerts: {outcome_cols}")

    # (b) Does the candidate population itself survive?
    pop = run(
        f"SELECT COUNT(*), COALESCE(MIN(alert_date)::text,''), "
        f"COALESCE(MAX(alert_date)::text,'') FROM mi_ep_alerts "
        f"WHERE source='historical_scan' "
        f"AND alert_date BETWEEN '{WINDOW_FROM}' AND '{WINDOW_TO}'")[0]
    n_surv, d0, d1 = int(pop[0]), pop[1], pop[2]
    print(f"  surviving historical_scan rows in the Phase-B window: {n_surv} "
          f"of {PHASEB_TOTALS['candidates']} ({d0}..{d1})")
    if n_surv < PHASEB_TOTALS["candidates"] * 0.5:
        missing.append(
            f"The candidate population: only {n_surv}/{PHASEB_TOTALS['candidates']} "
            f"mi_ep_alerts source='historical_scan' rows survive in-window "
            f"({d0}..{d1}) — the 2025-06-09..~2026-04-10 span was deleted "
            f"(delete_historical_alerts exists for idempotent re-runs; a later replay "
            f"cleared it). Tier labels for the deleted span are gone with the rows.")

    # (c) Any surviving rows on non-Bull days? (The entire non-Bull cluster is
    # 2026-03-21..2026-04-09 — see Stage 2.)
    nb = run(
        f"SELECT COUNT(*) FROM mi_ep_alerts a "
        f"JOIN mi_market_regime r ON r.regime_date = a.alert_date "
        f"WHERE a.source='historical_scan' "
        f"AND a.alert_date BETWEEN '{WINDOW_FROM}' AND '{WINDOW_TO}' "
        f"AND r.regime <> 'Bull'")[0][0]
    print(f"  surviving in-window rows on non-Bull regime days: {nb}")
    if int(nb) == 0:
        missing.append(
            "Non-Bull-day candidates: ZERO surviving rows fall on a non-Bull regime "
            "day — even the tier axis of the crisis-cluster cohort is unrecoverable.")

    # (d) The two source CSVs (checked out-of-band 2026-07-17; recorded here for the
    # provenance trail — a filesystem search is not a SELECT, so it is not re-run live).
    missing.append(
        "`replay268_phaseB.csv` + `replay268_tiers.csv` (the _killscale_bands_268.py "
        "inputs): absent from the local repo/home, the prod host (incl. /tmp, "
        "/home/apollo), all containers, and the oldest on-host pg backup "
        "(apollo-20260710.sql.gz — its mi_ep_alerts COPY block holds only 123 in-window "
        "historical_scan rows, 2026-04-06+). Verified 2026-07-17.")

    if missing:
        print("\n  ❌ EXACT RE-CUT NOT REACHABLE READ-ONLY FROM PROD. Missing:")
        for i, m in enumerate(missing, 1):
            print(f"    {i}. {m}")
        print("\n  → falling through to the reachable (regime-composition) analysis.\n")
        return False
    return True


def stage2_reachable_analysis(run) -> None:
    """Stratify what survives: the regime composition of the calibration window + a
    pro-rata per-regime exposure estimate from the preserved monthly candidate table."""
    print("## Stage 2 — reachable analysis (regime composition of the window)\n")

    # Regime-day composition, trading days only (mi_market_regime has weekend rows —
    # 2 of the 13 Crisis rows are Saturdays; exclude dow 0/6).
    comp = run(
        f"SELECT regime, COUNT(*) FROM mi_market_regime "
        f"WHERE regime_date BETWEEN '{WINDOW_FROM}' AND '{WINDOW_TO}' "
        f"AND EXTRACT(dow FROM regime_date) NOT IN (0,6) "
        f"GROUP BY regime ORDER BY 2 DESC")
    total_wd = sum(int(r[1]) for r in comp)
    print(f"  weekday regime rows {WINDOW_FROM}..{WINDOW_TO} (n={total_wd}):")
    for regime, cnt in comp:
        print(f"    {regime:<11} {int(cnt):>4}  ({int(cnt) / total_wd * 100:.1f}%)")

    # The non-Bull cluster (weekdays).
    cluster = run(
        f"SELECT regime_date::text, regime FROM mi_market_regime "
        f"WHERE regime_date BETWEEN '{WINDOW_FROM}' AND '{WINDOW_TO}' "
        f"AND regime <> 'Bull' AND EXTRACT(dow FROM regime_date) NOT IN (0,6) "
        f"ORDER BY regime_date")
    print(f"\n  non-Bull weekdays ({len(cluster)} — note they form ONE contiguous "
          f"cluster, the March-2026 crash):")
    print("    " + " · ".join(f"{d}({g[:4]})" for d, g in cluster))

    # Label provenance: created_at fingerprint of the window's regime rows.
    prov = run(
        f"SELECT MIN(created_at)::date::text, MAX(created_at)::date::text "
        f"FROM mi_market_regime WHERE regime_date BETWEEN '{WINDOW_FROM}' AND "
        f"'2026-02-28'")[0]
    print(f"\n  label provenance: 2025-06..2026-02 regime rows created "
          f"{prov[0]}..{prov[1]} (BACKFILLED — live labeling began ~2026-03-19; "
          f"every backfilled label is Bull).")

    # Pro-rata per-regime exposure estimate: month candidates × (regime weekdays /
    # month weekdays). Per-day candidate counts are unrecoverable, so this is the
    # finest honest grain; candidate flow is NOT uniform within a month (crash weeks
    # plausibly produce atypical EP-gapper counts) — treat as an order-of-magnitude
    # estimate, not a measurement.
    per_month = run(
        f"SELECT to_char(regime_date,'YYYY-MM'), regime, COUNT(*) "
        f"FROM mi_market_regime "
        f"WHERE regime_date BETWEEN '{WINDOW_FROM}' AND '{WINDOW_TO}' "
        f"AND EXTRACT(dow FROM regime_date) NOT IN (0,6) "
        f"GROUP BY 1, 2 ORDER BY 1, 2")
    month_wd: dict[str, int] = {}
    for m, _reg, cnt in per_month:
        month_wd[m] = month_wd.get(m, 0) + int(cnt)
    est: dict[str, float] = {}
    for m, reg, cnt in per_month:
        cands = MONTHLY_CANDIDATES.get(m, 0)
        est[reg] = est.get(reg, 0.0) + cands * int(cnt) / month_wd[m]

    n_cand = PHASEB_TOTALS["candidates"]
    n_sim = PHASEB_TOTALS["judge_high_simulated"]
    print(f"\n  pro-rata per-regime exposure estimate "
          f"(candidates n={n_cand}; judge-HIGH simulated cohort n={n_sim} scaled "
          f"proportionally):")
    print(f"    {'regime':<11} {'est. candidates':>16} {'share':>7} "
          f"{'est. n in envelope cohort':>26}")
    for reg in sorted(est, key=est.get, reverse=True):
        share = est[reg] / n_cand
        print(f"    {reg:<11} {est[reg]:>16.0f} {share * 100:>6.1f}% "
              f"{share * n_sim:>26.0f}")

    # The envelope card + the sample floor, for the verdict block.
    env = CALIBRATION_ENVELOPE
    print(f"\n  envelope under test ({env['source']}): exp {env['expectancy_r']:+.2f}R · "
          f"win {env['win_rate'] * 100:.0f}% · t20 p5 {env['trailing20_p5_r']:+.2f}R / "
          f"min {env['trailing20_min_r']:+.2f}R · maxDD {env['max_dd_r']:.1f}R · "
          f"streak {env['worst_streak']} · band sample floor n={_SAMPLE_FLOOR}")

    nb_est = sum(v for k, v in est.items() if k != "Bull")
    print(f"""
## Verdict (analysis only — feeds the quarterly band review; no live change)

  1. The '12-month mixed-regime window' is ~{est.get('Bull', 0) / n_cand * 100:.0f}% Bull
     by estimated candidate exposure ({total_wd - len(cluster)}/{total_wd} weekdays).
     The #268b envelope is a BULL-CONDITIONAL envelope, mechanically.
  2. Estimated non-Bull exposure: ~{nb_est:.0f} candidates → ~{nb_est / n_cand * n_sim:.0f}
     simulated envelope-cohort trades, ALL from one contiguous 3-week episode
     (2026-03-21..2026-04-09). A per-regime envelope cut from this window would be
     n<{_SAMPLE_FLOOR}-per-regime noise with ZERO independent episodes — no valid
     Crisis/Correcting/Choppy envelope exists in this data.
  3. So the honest answer to 'does the mixed window misprice any regime' is:
     it does not PRICE non-Bull regimes at all. The bands' 'never fires on healthy
     variance' guarantee is a Bull-year guarantee.
""")


def main() -> None:
    ap = argparse.ArgumentParser(description="#454 regime-stratified envelope re-cut")
    ap.add_argument("--ssh", default="apollo@87.99.134.162",
                    help="prod ssh host (runs read-only psql SELECTs via docker exec)")
    args = ap.parse_args()
    run = make_runner(args.ssh)
    print(f"# 454 regime-stratified envelope re-cut — window {WINDOW_FROM}..{WINDOW_TO}\n")
    if not stage1_attempt_exact_recut(run):
        stage2_reachable_analysis(run)


if __name__ == "__main__":
    main()
