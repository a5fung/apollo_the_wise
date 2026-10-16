# #686 frozen read — READY CHECK (Fri 2026-10-16, ~09:45 PT)

**Verdict: READY.** Nothing in the code or the pull blocks Saturday. One external dependency: tonight's
17:00 ET (14:00 PT) `nightly_data_pull` must write the 10-16 daily bar. If it does not, the read refuses
(exit 4) and nobody sees an outcome. Read-only throughout; no frozen file touched, no prod contact, no
commit. The registration and scripts were NOT edited.

## 1. Pins OK? YES

- The script's own `freeze_check()` returns no problems: script, `extract.sh`, doc body, the seven
  `_684` code/data files, `_684/daily.tsv.gz`, and the 63-draw pin all match the doc footer.
  One-line re-check (writes nothing): see step 1 of the sequence below.
- Git: none of the pinned files changed since the freeze (last touch 2026-10-04 `fd54e165`, #684
  files 2026-09-28). Freeze merge `4e761ae5` is an ancestor of `main`; `main` = local `origin/main` = `d4a7b8d2` (not re-fetched).
- Calendar re-derived: 15 block sessions (09-04 … 09-25); the 15th session after 09-25 is **10-16**.
- **Machine dependency:** `_684/daily.tsv.gz` is gitignored (hash `ac1afb24…`, present and matching
  on this laptop). Run Saturday from `/Users/alvinfung/apollo_the_wise` on this laptop. A fresh clone or
  worktree fails the freeze check with "file missing" and cannot be repaired by re-pulling (the bytes
  would differ).

## 2. Readable from when

- **Data:** `nightly_data_pull` fires 17:00 ET Mon–Fri (`scheduler.py`); right after a splits check it
  writes the day's grouped-daily bars into `mi_daily_closes`. Normally in by ~17:05–17:20 ET
  (14:05–14:20 PT); the job has a 45-min hard cap (17:45 ET, #672). A hang AFTER the ingest does not
  remove the bar; a hang BEFORE it does (09-18 deadlocked at 17:00 ET until a 00:16 restart).
- **Gates:** `extract.sh` and the read both refuse until the PT date is 10-17 (verified: both exit 3
  today). First legitimate moment = **00:00 PT Saturday**. The read adds a data gate: refuses (exit 4)
  unless the pulled file has a SPY bar dated >= 2026-10-16.
- **If Friday's pull fails:** `ingest_daily` skips weekends, so Saturday does not backfill it by itself.
  `job_recovery` re-runs a missed slot with its date pinned, Friday's chain recoverable until Monday
  09:30 ET, but only at the next market-agent BOOT (per its docstring; not exercised here). That is how
  09-18 was healed (SPY has no hole through 09-25 in the 09-28 snapshot). A failure with no restart
  needs a manual 10-16 ingest on prod = a prod write = operator/orchestrator, not a card.
  Tell-tale: no `nightly_data_pull` success notice Friday evening.

## 3. Inputs present? (extract.sh has no --check mode; read + simulated instead)

`extract.sh` runs 11 pulls over ssh -> `docker exec apollo-postgres psql`. Verified without touching prod:

- `bash -n` clean. Full flow run in a scratch mirror with a fake `ssh` and a shimmed `date`: all 11
  pulls issue, `pulled_at` is written, exit 0.
- All 11 SQL statements **parse** (libpg_query via pglast). Column references cross-checked against
  #684's prod schema snapshot (`_684/schema.txt`, 09-28): no unknown column. (A flagged `r.ep_score`
  hit is an alias collision in my checker — `raw r` vs `mi_alert_rank_shadow r` — and the same CTE ran
  in #684.) The only new SQL vs #684 (`first_high_time`, the `ah` lateral, `trades.tsv`) uses columns
  that exist (`mi_ep_alerts.score_tier/created_at/source`, `mi_live_trades.*` per `db.py`).
- Schema drift since 09-28: the only `DROP COLUMN` in `db.py` is `mi_stock_scores.market_cap` — not
  selected by any pull. No RENAME.
- Retention covers the block (<= 43 days old on 10-17): `mi_daily_closes` forever, `mi_intraday_bars` 5y,
  `mi_ep_alerts` / `mi_alert_rank_shadow` forever, `mi_stock_scores` + `mi_themes` 365d,
  `mi_ep_catalyst_metrics` 180d; `mi_ep_scan_log`, `mi_live_trades`, `mi_market_regime`,
  `mi_ticker_overrides` have no purge.
- ssh: key (`id_ed25519`, agent shows `apollo-laptop2`) and the host's `known_hosts` entry exist locally.
  **Not exercised** (no prod contact). Last captured successful prod pull from this checkout:
  `scripts/probes/_verify_1012_eve/687/q6.pulled_at` = 2026-10-12 22:28 UTC.
- A missing table/column cannot fail quietly: `set -euo pipefail` + `ON_ERROR_STOP=1` abort `extract.sh`
  at that pull with psql's error. A missing OUTPUT file makes the read exit 4 *before* STEP 0, so no
  STEP 0 alarm fires on an absent input. Valid pull = 11 files in `data/` AND `data/extract.pulled_at`
  (written last).
- Labelled EPs inside the block: none (`operator_labelled_eps.md` parses; PENG is 10-07, outside), so the
  per-draw "labelled EPs in favourable" column reads `none` — expected, not a defect.

## 4. Dry run (the script's built-in mode) — byte-identical

`--dry-run-old-block` (freeze check ON) run in a hermetic scratch copy so the repo's `out/` was not
touched: exit 0 in 54 s; `dryrun_step0.txt`, `_results_out.txt`, `_cuts.tsv`, `_outcomes.tsv`,
`_summary.json` all **byte-identical** to the committed 10-04 files (Python 3.14.6, this laptop). So the
frozen REPRO step will pass Saturday unless the Python environment changes — do not upgrade packages
before then.

**Real-read branch smoke (the code both dry-run modes skip).** The default read's `else` branch
(`features.main()` on `data/`, `trades.tsv`, the HIGH columns, the SPY data gate) had never executed.
In the scratch mirror I built a synthetic `data/` from #684's captured 08-15..09-03 rows (the three
#686-only pop columns derived from #684's alert columns), then ran the real branch through a wrapper that
only patches the date constants (no file edited): `--step0-only` exit 0 (63 rows, 17 HIGH, alarms none,
labelled MRNA found, 9 orderable all with an order record, 0 model misses) and the full read exit 0 in 52 s,
frame A 4 runners in 63 rows with 1 PASS (dollar volume, sign-only), the same headline as #684 and the
dry run. So no code path of the Saturday run is untested except the live pull and the real September data.
Orderable reads 9 not the dry run's 10 only because the synthetic HIGH-alert times are approximations.

## 5. STEP 0 alarm headroom (history from #684 `features.tsv`; expected to clear)

- Rows 40..200: May–Aug ran 5–9.4 scored/day -> ~75–140 expected for 15 sessions (doc says 75–120;
  between 120 and 200 is not an alarm, just outside the doc's guess).
- HIGH >= 5: the old 63-row held-out had 17 HIGH.
- Short history <= 3: 3 rows in all 670 (all May); no 15-date window above 3.
- 09:45 coverage >= 80%: May 94%, **Jun 74%** (before the capture audit), Jul 92%, Aug 94%, early Sep 100%.
  This is the one alarm that rides on nightly jobs having run on every one of the 15 days
  (`alert_day_path_persist`, #605 candidate persistence). If it trips for a real missing-bars reason, no
  re-pull fixes it — see section 7.

## 6. Saturday command sequence (this laptop, any time after 00:00 PT Sat 10-17)

```
# 1. pins (writes nothing). Expect: PINS OK
cd /Users/alvinfung/apollo_the_wise && git pull origin main
PYTHONDONTWRITEBYTECODE=1 python3 -c "import sys; sys.path.insert(0,'scripts/probes/_686'); import preregistered_read as p; print(p.freeze_check() or 'PINS OK')"

# 2. the ONE prod pull (read-only, $0) -> scripts/probes/_686/data/. wc -l per file = rows + 2.
bash scripts/probes/_686/extract.sh

# 3. dates-only sanity BEFORE the read (no price read). Expect: SPY rows 410, last 2026-10-16, missing []
python3 - <<'EOF'
import gzip, exchange_calendars as x
spy=[l.split("|")[1] for l in (l.rstrip("\n") for l in gzip.open("scripts/probes/_686/data/daily.tsv.gz","rt")) if l.startswith("SPY|")]
cal=[d.strftime("%Y-%m-%d") for d in x.get_calendar("XNYS").sessions_in_range("2025-03-03","2026-10-16")]
print("SPY rows",len(spy),"last",spy[-1],"missing",[d for d in cal if d not in set(spy)])
EOF

# 4. composition only, no outcome computed. exit 6 = alarm, 4 = file/10-16 bar missing, 5 = REPRO mismatch, 2 = pin mismatch
python3 scripts/probes/_686/preregistered_read.py --step0-only

# 5. the read, ONCE (about 1-3 min) -> out/686_step0.txt, 686_results_out.txt, 686_cuts.tsv, 686_outcomes.tsv, 686_summary.json
python3 scripts/probes/_686/preregistered_read.py
```

Then the one-paragraph proposal per doc §10 (his ruling; THE LINE). What gets committed (the non-ignored
`data/*.tsv`, `out/686_*`) is the orchestrator's call. Run it from the main session or his terminal, not a card:
step 2 is a prod ssh and card prod reads have been refused lately.

## 7. If something blocks — what and who

- **10-16 bar missing (exit 4 / SPY last < 10-16):** Friday's pull failed. Check for #312 recovery at
  the next boot; else manual prod ingest — **operator/orchestrator** (prod write). Re-run steps 2–4 after.
- **Pin mismatch (exit 2):** a pinned file changed or the run is on another machine — restore from git /
  use this laptop. **Orchestrator.** Never re-pin silently.
- **STEP 0 alarm (exit 6) caused by the PULL:** the doc says fix the pull, re-pull, re-run `--step0-only`.
  ⚠ Latent ambiguity: `extract.sh` is itself hash-pinned, so editing it trips the freeze check; a query
  fix therefore needs a footer re-pin. Whether that is allowed is **the operator's ruling**, not mine.
  Today (10-16, before any outcome is on disk) is the last clean window for any `extract.sh` change;
  I found nothing that needs one.
- **STEP 0 alarm from missing DATA (e.g. coverage < 80% because bars were never stored):** no pull
  fixes it; the registration does not say what then. **Operator's ruling.**
- **Exit 5 (REPRO mismatch):** environment drift (Python/numpy). Restore the environment that
  reproduced today; **orchestrator**. The read writes `out/686_INVALID.txt` and has opened nothing new.

## 8. Not done

- No prod contact: ssh reachability, container name, real row counts, whether Friday's pull succeeds —
  all first visible Saturday (step 2 output) or in Friday's notice.
- SQL was parse-checked and column-cross-checked, not executed; type/semantic errors on real data would
  surface as a psql error that aborts step 2 cleanly.
- Scratch evidence (session-local): `…/scratchpad/mirror/` (hermetic copy + dry-run outputs),
  `…/scratchpad/c686/` (fake ssh/date shims, `sql2/` = the 11 statements as sent, `parse_sql.py`,
  `build_smoke_data.py`, `smoke_real_branch.py`, `smoke_step0.out`, `smoke_full.out`).
