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
