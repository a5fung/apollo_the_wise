# #684 — what, known on the gap day, marks the EPs that run big? (2026-09-28)

Read-only, $0 probe. Doc: `docs/analysis/684_ep_runner_selection_2026-09-28.md`.

Order of execution (each reads the files the previous step wrote; nothing re-pulls):
1. `gate.sql` → `gate_sql_out.txt` (composition of the scored population, run once on prod);
   `gate_alarms.sql` → `gate_alarms_out.txt` + `gate_alarms_alerts_by_date.txt` (the three alarms run down).
2. `extract.sh` → `pop.tsv hist.tsv scores.tsv themes.tsv prior.tsv orb.tsv regime.tsv sector.tsv daily.tsv.gz`
   (the ONE pull; `daily.tsv.gz` is gitignored, 4 MB).
3. `gate.py` → `gate_out.txt` — STEP 0, composition only, no outcome.
4. `features.py` → `features.tsv` — STEP 1, every feature tagged PRE / 0930 / 0945 / CLOSE / ALERT; no forward bar read.
5. `study.py` — STEP 2 pre-registration in its docstring; STEP 3 the one run → `results_out.txt`,
   `results.tsv`, `runners_dropped.txt`, `outcomes.tsv`, `summary.json`; `tables.md` renders `results.tsv`.
6. `posthoc.py` → `posthoc_out.txt` — labelled post-hoc: the 09-27 extension lead under its own definition;
   `diag_out.txt` — post-hoc diagnostics on the one passing feature and the reversed cluster.
`schema.txt` — the column schema of every table touched, pulled once.

ADDENDUM v1 (2026-09-28) — RETRACTED, kept on disk for provenance only, not read as a finding:
`orb_minutes.sql/.tsv`, `study_orb.py` → `orb_results*.tsv`, `orb_outcomes.tsv`,
`orb_conditional_on_fill.py` → `orb_conditional_out.txt`. Used a 09:30-09:44 15-minute "opening
range" that does not exist in the live code (the live ORB is the single 09:30 bar) — superseded by
v2 the same day. `study_orb_live.py` still imports `study_orb.per_feature/run_pass/fmt_rate`, so
this file stays; its OWN outcome numbers (orb_results.tsv etc.) do not.

ADDENDUM v2 (2026-09-28) — the live entry replayed bar-by-bar (current): `live_entry_bars.sql` (one
read-only pull, every 1-minute bar 09:30-16:00 ET for all 670 rows) → `live_entry_bars.tsv`
(236,265 rows, gitignored) → `study_orb_live.py` (imports `study.py` + `study_orb.py`; mirrors
`agents/market_intelligence/sustain_reject_replay.entry_walk` verbatim for the fill mechanics —
single-bar ORB, admission gates, 10:00 cancel post-2026-08-01, the real pipeline's own gate order) →
`orb_live_status_out.txt`, `orb_live_results.tsv` (frame B), `orb_live_results_A.tsv` (frame A′,
same population), `orb_live_outcomes.tsv` (per-row status/fill/outcome detail). Written up in
`docs/analysis/684_ep_runner_selection_2026-09-28.md` §Addendum 2026-09-28 — measured from the
actual live MAGNA53 entry.

FOLLOW-UP (2026-09-28) — late alerts (first pass 09:45-09:59 ET), three options: `late_alerts.py`
(pre-registered docstring) reuses `orb_live_outcomes.tsv` for the LATE/CONTROL population, `pop.tsv`
for scan times, `daily.tsv.gz` for forward sessions/prior closes, and one new pull
`live_entry_bars_full.sql` → `live_entry_bars_full.tsv` (236,265 rows, gitignored — the same
09:30-16:00 population as `live_entry_bars.tsv`, extended with CLOSE, which the exit-ladder walk
needs and the fill-only walk didn't). Fill mechanics reuse `study_orb_live.entry_walk`; P&L reuses
`agents/market_intelligence/live_fill_counterfactuals.walk_arm` (harvest="live_ladder") under
`rule_eras.exit_rules_as_of` (era D) — the same tool `sustain_reject_replay.py` already uses for an
identically-shaped question. Outputs: `late_alerts_out.txt`, `late_alerts_detail.tsv` (per-row
audit). Written up in `docs/analysis/684_ep_runner_selection_2026-09-28.md` §Late alerts (first pass
09:45–09:59): three options, replayed.
