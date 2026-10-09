# Delayed-entry shadow — first read of the live lane's real-tail rate (2026-10-09)

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.**

**Verdict: EXTEND — every cell is too thin to conclude.** The 33 mature fires hold one genuine
tail (a re-entry, not a first attempt); no rung reaches 30 mature fires at either level. Read again
with `delayed_entry_mid_november_reread` (2026-11-16). Nothing graduates, nothing changes (THE LINE).

Review: `data_gated_reviews.yaml` → `delayed_entry_shadow_first_read` (predicate read 33 against a
threshold of 30). Plan of record: `~/.claude/plans/crystalline-waddling-charm.md` (bands
pre-registered 2026-08-30). Probe files: `scripts/probes/_de_first_read/`.

## Method and population

- **Prod, read-only, three SELECTs, captured once:** `q1_schema_out.txt` (columns + the predicate:
  33), `q2_rows_out.txt` (all 131 trigger rows with fire_date ≥ 2026-08-31), `q4_screen_inputs_out.txt`
  (the EP-day screen inputs of the 36 lane campaigns since 08-20). Post-processed locally:
  `analyze.py`, `pstar_277.py`, `project.py` (outputs `*_out.txt` beside them).
- **Population read = the review's own:** `realized_r IS NOT NULL AND fire_date >= 2026-08-31 AND
  fire_date <= CURRENT_DATE - 30` → **33 fires, 14 campaigns (EP dates 08-27 → 09-08), fire dates
  08-31 → 09-09.**
- **"Genuine tail", quoted from the plan (Goal 1):** *"Of every EP-day name the scan sees, what share
  later produces a ≥4R campaign under each rung?"* Measured as **harvested `realized_r` ≥ 4** on the
  M-none arm (hard stop, exit at the 20-session close) — never MFE (plan §3: *"`realized_r` is
  HARVESTED R, never MFE"*). `reached_4r` (a touch flag) is reported beside it and agrees on every row.

**Composition of the 33:**

| cut | counts |
|---|---|
| outcome | 30 stopped at −1.00R · 3 held to the 20-session close · **0 still open** |
| rung | ep_close_620_prox 14 · ep_low_reclaim 10 · ep_close_reclaim 7 · ep_high_break 2 |
| attempt | 24 first attempts · 8 same-pattern re-entries · 1 new-high re-entry |
| screen_member | **8 true · 0 false · 25 unknown (NULL)** |
| pattern / screen version | v2 / screen_v1 on all 33 — no rung or screen definition changed mid-sample |
| settle version | settle_v3 28 · settle_v2 5 (v3 adds only the #616 variant columns; the incumbent's realized_r is the same walk) |
| recording lag | all 33 written the evening of the fire (0-day lag) — no backfill in the read |

- **The 09-27 maturity fix worked:** 0 open rows among mature fires and 3 non-stop outcomes are
  present, so this is no longer a losers-first sample.
- ⚠ **Surprise — "screened" is really "screened vs unknown".** no mature fire is screened OUT (`screen_member` can be false — ACN 10-01 on the watch table — but no
  screened-out name has fired yet); it is NULL whenever any EP-day input is missing. The six 08-27/08-28 campaigns have no catalyst grade and
  no extension on their day-0 watch row; AGX, IONQ, QCOM (and later DFTX, SRRK, INTC, MSTR, AKAM, WOLF)
  have a grade but no extension. 61 of the 131 prospective rows are NULL. So the screened cell grows
  at about half the raw rate, and the raw-minus-screened gap cannot yet be read as "the value of
  selection". (Recording gap reported here; no task opened.)
- **Eras:** no lane definition changed. On the admission side, the 2026-09-13 theme-bonus change
  (`docs/setups/magna53_ep.md`) alters which names alert from 09-14 onward; all 33 mature fires come
  from EP dates ≤ 09-08, so this read sits wholly before it. The 09-06 exit change touches live MAGNA53
  trades, not this lane's arm. **The sample also straddles two earlier admission changes** (verifier): 16 of
  the 33 fires (the six 08-27/08-28 campaigns, CRWD's tail among them) were admitted before the 08-29
  extension revert (75% → 50%) and around the 08-27 real-time gap floor; their extension is NULL on the
  watch row, so whether any was 50-75% extended cannot be told. **Decided (not his call — a reporting
  choice):** the November read reports pooled AND split at EP date 09-14 (the theme-bonus change) and
  08-29.

## The per-rung table (mature settled fires; tail = harvested R ≥ 4)

| rung | raw: tails / fires | first attempts only | screened: tails / fires | band |
|---|---|---|---|---|
| ep_close_620_prox | 0 / 14 | 0 / 8 | 0 / 4 | too few — extend |
| ep_low_reclaim | **1 / 10** (CRWD re-entry, +22.4R) | 0 / 7 | 0 / 1 | too few — extend |
| ep_close_reclaim | 0 / 7 | 0 / 7 | 0 / 2 | too few — extend |
| ep_high_break | 0 / 2 | 0 / 2 | 0 / 1 | too few — extend |
| **all rungs** | **1 / 33 (3.0%)** | **0 / 24** | **0 / 8** | too few — extend |

- **Per-cell bar used:** the review's own threshold of 30, applied per cell (the action says "too few
  settled fires → extend" per cell). Every cell is under it.
- **The ep_low_reclaim "1 in 10" is NOT a ≥10% band hit:** one tail in ten fires is consistent with a
  true rate anywhere from well under 1% to about 45%.
- The one tail: CRWD (EP 08-27), a same-pattern re-entry on 09-03 held to the close for +22.4R. Its
  first low-reclaim attempt on 09-02 stopped at −1R under the lane's stop; the #616 wider stops on that
  same first fire would have harvested +8.0R (0.75× ADR) and +6.0R (1× ADR).

## Break-even rate p\* restated on the 277 real-EP campaigns

The published p\* (campaign-policies doc §7) blended the outcome-selected missed-EP events against the
stopped-44. Restated here on the 277 live EP campaigns (`scripts/probes/_327_real_ep/fires.tsv`,
`reentry_rows.tsv`, settled rows only) with a **different construction, stated plainly:** fire-level,
within the 277, tail (harvested R ≥ 4) vs non-tail mean R on the **lane's own M-none arm, incumbent
stop** — the quantity the live `realized_r` measures. p\* = −mean(non-tail) ÷ (mean(tail) − mean(non-tail)).

| rung (first attempts, ERA A+B) | n | tails | rate seen on the 277 | restated p\* |
|---|---|---|---|---|
| ep_close_reclaim (≈ M1's entry) | 150 | 4 | 2.7% | **7.1%** (published M1: positive at 0%) |
| ep_low_reclaim | 213 | 9 | 4.2% | 9.5% |
| ep_close_620_prox | 216 | 10 | 4.6% | 10.9% |
| ep_high_break | 49 | 2 | 4.1% | 10.7% |
| all first attempts | 628 | 25 | 4.0% | 9.5% |
| all attempts incl. re-entries | 1,266 | 51 | 4.0% | 7.9% |
| new-high re-entries (≈ R3) | 107 | 0 | 0% | cannot break even on this data |

- **B-EPC and the L-family cannot be restated:** the lane records no +2R-partial/breakeven arm and no
  composites; the trail arm is not either of them.
- **Consequence 1:** on real EPs every rung needs ~7–11% genuine tails to break even, so the
  pre-registered "2–10% → bring the SIMPLE policy" band now sits mostly inside the losing region. The
  bands are applied as pre-registered for this read; they need re-registering against the restated p\*
  before the next one.
- **Consequence 2:** the 277's own tail rate (2.7–4.6%) is below its restated p\* on every rung — the
  arm did not break even on its calibration data either, consistent with the #327 close (2026-10-08).

## Next read

| cell | 30 mature fires reached about |
|---|---|
| ep_close_620_prox raw | 2026-10-22 (already fired, maturing) |
| ep_low_reclaim raw | 2026-10-23 (already fired) |
| ep_close_reclaim raw | 2026-11-06 (already fired) |
| ep_close_620_prox screened | ~2026-11-09 (projected at 5/week) |
| ep_close_reclaim / ep_low_reclaim screened | ~11-29 / ~12-03 (projected) |
| ep_high_break | not before spring 2027 at ~1 fire a week |

- **Recommendation:** read again with `delayed_entry_mid_november_reread` on **2026-11-16** — three raw
  cells and the screened 620 cell will have ≥30; the other screened cells will still be thin and
  should be reported as counts.

## What this does not answer

- **Whether any rung pays.** 33 fires, 1 tail; no cell can separate a 1% rate from a 10% one.
- **The screened rate.** 25 of 33 rows have unknown screen membership; 8 known members is not a rate.
- **Whether the bands are still the right ones** — the restated p\* says they need re-registering; that
  re-registration is not done here.
- **B-EPC, R3 and the L-family as policies** — the lane does not record their management or composites.
- **Era effects** — the November read reports pooled and split at 08-29 and 09-14 (decided above); this read is too small to split.
- **The restated p\* overlaps this review's own fires:** ERA B in `_327_real_ep/fires.tsv` is exactly the live lane's campaigns, captured 09-26 while still immature (35 stops at -1R, 1 open), so pooling A+B puts the same fires into p\* at their stop-only stage. An ERA-A-only restatement is due with the November read; it does not change today's verdict (every cell is too small).
- **Anything about the #616 wider stops as a rule** — the CRWD figures are one fire; that question
  belongs to `delayed_entry_adr_stop_variant_616`.

⚖ **THE LINE:** measurement only. No stop, entry, exit, size, safeguard or lane setting is changed or
proposed; promotion would still need CHANGE_PROCESS, his sign-off, a runtime toggle and shadow-first.
