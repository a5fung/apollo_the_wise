# Backtest data audit — the STEP 0 data gate

The standard these scripts enforce: **`docs/methodology/backtest_data_standard.md`** (taxonomy of problem families, the gate table
G1..G10, the positive controls, how a backtest is run here, the fix queue). Read it first; this file is the how-to.

Everything here is **$0, offline, read-only on the data**. Every script drops bars after `--cutoff 2024-12-31` at read time and
refuses a later cutoff — the 2025-26 table is sealed. Stdlib + pandas/numpy only. Every printed number carries its n.

## One command

```bash
bash scripts/backtest_data_audit/run_all.sh ~/apollo_data/cb702_pre A ~/apollo_data/cb702     # era A, era B as the richer export
bash scripts/backtest_data_audit/run_all.sh ~/apollo_data/cb702 B                               # era B alone
OUT=/path FAST=1 bash scripts/backtest_data_audit/run_all.sh <era-dir> <label> [richer-dir]      # skip the minute-reading steps
```

It runs the selftests, then every lens in the order below, saves each console as `<OUT>/<step>.console.txt`, the TSVs under
`<OUT>/{universe,dup,price,sectype,pit}/`, and ends with `gate_verdict.py`, which prints the G1..G10 table with PASS / REFUSE /
REPORT. **Exit 2 = at least one REFUSAL: the read does not start.** Exit 1 = a lens crashed. Nothing in the chain aborts early — the
gate wants all readings. Sidecars are picked up by presence in the era dir (`daily_raw_close.csv.gz`, `symbol_guard.tsv`,
`cb702_splits.psv`, `cb702_sic.psv`, `small_pulls.psv`, `minutes/`, `out/{entries,candidates,watch,trades}*`); a missing one skips
the flag that needs it and the log says so. Full run on era A against era B, minute scans included: about 2.5 minutes (measured
2026-10-23: universe 22s, duplicate 19s, price 28s, security type 21s, pit entries 26s, overlap 12s, the rest under 10s each).

A new or rebuilt export (the delisted refetch, a vendor re-pull) gets the whole run **before its first read**, and the console goes
into the read's registration doc.

## The lenses, in order (what each answers, the gate it feeds, its exit code)

| step | script | answers | gate | refuses via |
|---|---|---|---|---|
| 0 | `*.py --selftest` | can each check see its own planted defect? (universe plants 5; price injects one per check; duplicate plants exact / near / scaled / coincidence; security tests the name classifier) | S0 | non-zero rc |
| 1 | `universe_check.py --export E --label L --other RICHER --guard --splits --sic --small-pulls --raw-close --assets --out-dir D` | integrity, coverage by year, stale bars, duplicate companies, non-equity items, identity breaks (writes `symbol_guard_<L>.tsv` in the runner's `--breaks` format); with `--other`: overlap, identity across exports, the known-gone list, runner coverage. `--selftest` plants 5 defects | G1 G2 G4 (+F6 tripwires) | exit 0 always — `gate_verdict.py` reads the verdict lines and `liquid_per_session_by_month.tsv` |
| 2 | `duplicate_series_check.py E --label L --out D [--vs RICHER]` | one company under two symbols: strict twins (byte-identical OHLCV), scaled twins (same company, different price scale), share-class copies; `dedupe_map.tsv` says which symbol to drop; `--vs` adds the cross-era seam | G3 | exit 0 — verdict reads `CONFIRMED strict pairs=` and `TEST 2 scaled twins ... pairs=` |
| 3 | `price_integrity_check.py --export E --label L --out-dir D --raw-close R \| --splits S --sectype small_pulls.psv [--compare RICHER]` | OHLC order, price levels, ≥25% gaps classed (reverted / persistent / known adjustment), vendor-booked adjustment factors that break the series, spin-off candidates, split-like ratios, calendar holes, zero volume, wicks, test symbols, duplicates, cross-export close ratios. **Positive controls** OPLN 2019-06-28, ZWS 2021-10-05, BEP 2020-07-30 must be FLAGGED or NOT_TESTABLE with a reason | G5 (+G1) | **exit 3** when a testable control is not flagged |
| 4 | `security_type_check.py --export E --era L --raw-close R \| --splits S --small --sic --assets --watch-start --watch-end --cutoff --max-unknown-share 0.02 --verified-real <list> [--breaks guard] [--vs-export RICHER --vs-splits S] [--impact watch.tsv.gz] --out D` | which admitted tickers have no type (admitted "as prod does"), which pass the filters but are ETNs / funds / SPAC shells (the hand-verified list of 23 lives in `run_all.sh`), the type source and its snapshot date, OTC-today, SPAC trust-price phase, $5-floor units raw vs adjusted, dollar-volume split invariance | G6 | **exit 3** when untyped admitted nights > 2% (or `--max-verified-nights` is set and exceeded) |
| 5 | `pit_lint.py lint --out D` | the 33-item static checklist (non-point-in-time inputs, look-ahead, feed/calendar, walk assumptions) with a code anchor per item, its guarding test and its measurement | G7 | **exit 1** when an anchor moved (the checklist is stale against the code) |
| 6 | `pit_lint.py calendar --export E [--minutes DIR] --label L --out D` | sessions per year vs NYSE, the unscheduled closures, early-close days and the after-hours minute bars the fetcher keeps on them | G9 | exit 0 — verdict reads the per-year lines |
| 7 | `pit_lint.py inputs --data ERA_DIR --start --end [--raw-close] [--breaks] --assets --label L --out D` | universe member-nights resting on a non-PIT input: no type, fund-like name, no SIC group, regex exclusions | F7 report | — |
| 8 | `pit_lint.py horizon --data ERA_DIR --candidates C --k tl [--breaks]` · `chain --watch W --candidates C` · `entries --entries T --k tl [--minutes DIR --candidates C]` | walks whose data ends inside the 121-session window (dropped as "degraded"), walks crossing the seal; the chain key recomputed point-in-time; entry-time facts: stop from the fill minute's own low, fills on early-close days, minute-vs-daily abstains, fill-at-level share, **the R cost of 0.1% exit slippage (W2)** | F8/F10 report; the W2 line is printed in the verdict | — |
| 9 | `pit_lint.py overlap --era-a DIR --era-b DIR --out D` | the same dates (2022-03-28..06-30) through both exports: universe membership, the RS percentile, vendor OHLCV agreement | G10 | — |
| 10 | `trade_impact.py --flags D/<L>_flags.tsv --export E --trades T --label L --kind c0\|r1 [--cell]` | for the trade list you are about to quote: trades entered after the cutoff, holds that run past the last kept bar (sealed dependence), and the trades whose hold or 60 pre-bars contain a flagged artifact, with mean R touched vs untouched | G8 | exit 0 — verdict reads the two sealed lines; **run it on every list you quote** |
| 11 | `gate_verdict.py OUT --label L` | the G1..G10 table from the consoles above | — | **exit 2** on any REFUSE |

## Reading the verdict

- **REFUSE** — the read does not open an outcome on this export. Era A on 2026-10-23: G2 (liquid ratio 0.852–0.867 vs ≥ 0.97; 335
  of 529 known-gone names missing), G3 (71 confirmed pairs + 27 scaled twins), G6 (8.35% of admitted nights untyped). Era B: G8 on
  the published C0 list (28 entered after the cutoff; 57 holds run past the last kept bar, the 28 included; of 8,984) — censor them.
  Both verdicts: `runs_2026-10-23/run_all_{A,B}/verdict.txt`.
- **REPORT** — not a refusal; the line goes beside the headline verbatim (the vendor gap, the after-hours minute count, the W2 cost).
- **PASS** — the threshold in the standard's §2 table was met.

## Where the 2026-10-23 runs are

`runs_2026-10-23/universe/` (console + every TSV from `universe_check.py`, A vs B), `runs_2026-10-23/{A,B}_*` (price integrity +
trade impact), `out_1023/` (security type), `../probes/_705_dup_series_1023/` (duplicates + the trade join),
`../probes/_705_pit_1023/` (point-in-time). The earlier probes that found the families: `../probes/_705_corp_actions_1023/`,
`../probes/_705_survivorship_1023/01_fetch_delisted.py` (the refetch, runs on the server).

## Rules every reader of an export follows (the loader contract)

`keep_default_na=False` and `dtype={ticker: str}` (the ticker `NA` is Nano Labs, 620 rows in B); drop `volume == 0` and
`close <= 0` before any gap / base / history logic; drop the exchange test-symbol pattern; use the RAW close for every dollar
threshold; pass the era's `symbol_guard_<L>.tsv` as `--breaks`; never join another table by bare symbol across eras.
