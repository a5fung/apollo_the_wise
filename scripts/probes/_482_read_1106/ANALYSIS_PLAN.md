Order is fixed. Nothing that reads outcomes runs before step 1 is committed.

0. **Folder.** Use `scripts/probes/_482_cross_arm_1106/`, with `data/` for the CSVs and `out/` for outputs. The SQL files, data and outputs live only there, and the remote files carry unique names (e.g. `/tmp/482x_<file>.sql`).

1. **Pre-registration (main loop).**
   - Write the prereg text verbatim to `docs/analysis/482_cross_arm_read_prereg_2026-11-06.md`.
   - Add a pointer to it from PLAN.md's #482 line and from `bracket_geometry_variants_parked.cross_refs` in data_gated_reviews.yaml.
   - Commit and push, check `git show --stat HEAD`, and record the commit hash.

2. **Captures (main loop, read-only, on prod).**
   - Run each of the 7 SQL scripts once: `docker exec -i apollo-postgres psql -q -X -v ON_ERROR_STOP=1 -U <user> -d <db> < /tmp/482x_<file>.sql > <file>.csv`. `-q` keeps the SET tags out of the CSV.
   - Copy each file to `data/` and record row count + md5 in `data/MANIFEST.txt`.
   - Never re-run a capture to re-read it.
   - Assert that line 1 of every CSV is the header.

3. **Population checks.** Write `cross_arm_read.py` in the probe folder: read-only, CSV in, stdout + `out/results.json`. Its section 0 runs first and prints:
   - (a) The cohort list (id, ticker, alert_date, exit_rule, derived era, status) and two counts: the predicate (closed, alert_date ≥ 08-17) and the cohort (closed, fill ≥ 08-16). Report the actual numbers if they are not 20.
   - (b) Derived era vs recorder `exit_era` for each trade_id. **Any mismatch: STOP and report.**
   - (c) Rows per arm per fill by outcome class, and missing (pending) arms. There should be 15 walked arms + `fill_facts`.
   - (d) `target_r`/`breakeven_arm_r` on follows-live rows vs the era expectation (2/NULL in C, 8/3 in D and E). List disagreements.
   - (e) Fills with a non-NULL `pnl_attribution` (excluded) and `entry_attempt=2` fills (flagged).
   - (f) The `admission_era` mix per exit era.
   - (g) In era C, `harvest_legacy_2r` vs `live_replay` R_own, which should be equal. Also the share of fills where `stop_low_of_day` = `stop_orb_low`.

4. **Tier 1 tables (same script).**
   - **R_cap.** Compute it for every arm row with `book_geometry_arms.capped_dollar_r()`. Import it offline if the import works; otherwise reproduce `capped_risk_fraction` + `regime_risk_multiplier` + `risk_pct_at` exactly. On a control row with a NULL `stop_price`, use `live_stop`. Assert that stored `realized_r_capped` equals the recomputed value on book-arm rows (tolerance 1e-9).
   - **Fidelity table per era.** live_replay − live_actual for each fill; pass when within 0.25R.
   - **Per arm per era.** Every metric in the prereg §Tier 1: tail counts first, then paired deltas in R_cap and R_own, drop-best, tail-clip, rescues, the engine check vs live_replay, and the pct/adr deltas.
   - **Horizon rows.** List them separately with `mark_r`.
   - **Labels.** Apply the label rule mechanically, twice (marks excluded / marks counted), and print WATCH-LIST / NOT A CANDIDATE / UNREADABLE / UNRESOLVED per arm.
   - **"Disappoints" per era.** Report it, plus the `fill_facts` summary per era.
   - **No pooled totals.** The script must not print an all-era line.

5. **Tier 2 — copy of the 08-18 geometry script.** Copy `scripts/probes/bracket_geometry_read_482.py` to `bracket_geometry_read_482_cde.py` in the probe folder. Never edit the original. Required edits:
   - (E1) Add `ERA_D_START=date(2026,9,6)` and `ERA_E_START=date(2026,10,13)`. Change the signature to `era_of(ad, exit_rule=_UNSET)`:
     - E if `exit_rule=='depth'`, or (for an unstamped shadow row) `ad>=ERA_E_START`;
     - then D if `ad>=ERA_D_START`;
     - then C / B / A as before.
     - `enrich` passes `r.get('exit_rule') or None` for live rows and nothing for shadow rows.
   - (E2) Replace `assert len(shadow_raw)==42` with a printed count. Keep the quarantine assertion.
   - (E3) Change the era loops to `('C','D','E')`, and make mechanism-5's `r['era']=='C'` test `in ('C','D','E')`.
   - (E4) Make the ADR prints None-safe.
   - (E5) Add `--dump-json PATH`, writing the enriched rows: lane, id, ticker, alert_date, era, r, r_planned, adr_units, stop_dist_pct, reconstructed.
   - Run it with `--data-dir data --dump-json out/b482_dump.json > out/b482_cde.txt`.
   - Read only the per-pair rows and the by-era counts. Sections 3 and 4 are pooled or describe the retired +2R partial, so they are not read.
   - `cross_arm_read.py` pairs the dump per era, taking the era from the live twin, and applies the Tier 2 nominate rule.

6. **Tier 3 — copy of the 08-18 sweep.** Copy `scripts/probes/geometry_sweep_572.py` to `geometry_sweep_572_cde.py` in the probe folder. Required edits:
   - (F1) Import `d, era_of, f, pctl` from `bracket_geometry_read_482_cde`, and pass the row's `exit_rule` to `era_of`.
   - (F2) Skip the header row of `minute_bars_cohort.csv`. Load daily bars from `daily_bars.csv`, skipping its header (columns: ticker, trade_date, o, h, l, c).
   - (F3) Add a `target_px=None` kwarg to `simulate()`; None keeps every existing lane byte-identical. Add lane B2: real entry, stop = entry−2×(entry−orb_low), `target_px` = entry+2×(entry−orb_low). Skip it when entry ≤ orb_low.
   - (F4) Make C05/C10 skip a row whose `atr_14` is NULL instead of crashing.
   - (F5) Change the section-6 era loop to `('C','D','E')`.
   - (F6) Add `--dump-json PATH`: one rollup per lane×trade (lane, trade id, ticker, alert_date, era, r, adr_u, pnl_ps, n_attempts, partial, horizon, stop_pct), plus the excluded lists (thin, no bars, W no-entry, CPDL invalid, odd fills).
   - Run it with `--data-dir data --dump-json out/s572_dump.json > out/s572_cde.txt`.
   - `cross_arm_read.py` computes, per era: W vs B2 (no-entry = 0), and the re-entry increment A−B0 and Apdl−B0 on days a re-entry fired (conservative decides, optimistic shown). It applies the Tier 3 nominate rule.
   - C05 / C10 / CPDL are printed and not read.

7. **Recount before anything reaches him (main loop).** An independently written `recount.py`, sharing no code with `cross_arm_read.py`, recomputes three things from the raw CSVs:
   - the fidelity pass list;
   - the era-D `stop_adr_050` paired R_cap delta sum and n;
   - the era-C `entry_first_hour_bar` no-entry / entered / settled counts.
   All three must match exactly. A mismatch means fixing and re-running locally. Captures are never re-run.

8. **Results and report.**
   - Write `docs/analysis/482_cross_arm_read_2026-11-0X.md`: per-era tables with the tail first, the label per arm, the 5-minute and sweep sections labelled descriptive / nominate-only, and the cannot-answer list.
   - Add finding rows to `docs/setups/magna53_ep.md` and to `docs/setups/exit_discipline.md` (its ONE-read section). In the same commit, fix exit_discipline.md's stale "gated on era_d / 2026-09-06" text: the predicate is era_e / 2026-10-13.
   - Set `bracket_geometry_variants_parked` to answered, with the resolution, the per-era "disappoints" facts, and the re-arm date its notes allow.
   - Add a vault entry in `~/trading_vault`.
   - **Report to him in the CLAUDE.md format.** Line 1 is the answer, e.g. "#482 (bracket-geometry evidence lab) — first per-era read: <N> arms on the watch-list / none beat the live bracket; too few trades per era for a ruling". Then one bullet with his action: none, or the named fork. Geometry is THE LINE, so the decision stays his.
   - After it is reported, #482 may close per its own DONE-WHEN. The `docs/task_closes.md` entry gets BAR quoting the DoD ("a shadow lab logging realized-R per bracket variant → enough evidence for an informed operator geometry decision") and EVIDENCE = the results doc, the commit and the recount match.