# Shortlist pre-score replay — what changes when the graded 20 rank by the three-term pre-score instead of gap size (2026-08-22)

**MEASUREMENT of the shipped change. $0 — one prod read-only capture (psql), no LLM calls,
no paid data. The flip itself is operator-directed (see `docs/setups/magna53_ep.md` change log
2026-08-22); this replay is its evidence artifact.**

## The ask

The shortlist pre-score flip makes `run_ep_scan` rank each tick's candidates by
`ep_rubric.SHORTLIST_WEIGHTS` (liquidity 15×3 / flat gap 10×1 / theme 10×1, composite 0–65,
tie-break: continuous ADV$ then ticker) instead of gap size, and grades only the top
`SHORTLIST_SIZE` (20). Replay every historical board under BOTH keys: which names the new key
adds and drops, how the labelled real EPs fare, and the outcome distributions of both sets.

## The headline

**Zero labelled real EPs lose their grading slot anywhere in the replay, and six gain one that
gap denied them** — SNDK (#1), MU (#3), BE (#5) on 2026-04-08, ARM (#3) on 05-06, SNOW (#3) on
05-07, with QBTS lifted to the rank-22 boundary. MRNA 08-19, the operator's reference EP, keeps
its slot (gap rank 2 → pre-score rank 4). **The trade-off, stated plainly: the dropped set is
thin max-gap names with fatter raw 5-day spike tails that do not hold to the close, and 2 of
the 16 current-era historical HIGH alerts would have lost their grading slot (CRI 05-06, POWI
05-26 — both ordinary outcomes, neither labelled).** Stage 0's conclusion is unchanged and
restated: re-ranking recovers **at most one** of the 16 cap-attributed real EPs to a possible
*entry* (SNOW, conditional on an ungraded catalyst) — the score bar is the wall behind the cap.
The justification for this flip is coherence and future-proofing, not retention recovery.

Numbers behind that:

- **54 of 92 replayed boards change at all**; 525 name-days swap in each direction
  (≈5.7/day across the window; churn concentrates on flood mornings — 17 swaps on 04-08's
  119-name board, 16 on 05-06's 132-name board; quiet boards under 20 names are untouched
  since everyone is graded either way).
- **Who gets the slots**: median ADV$ of the added set is **$166M** vs the dropped set's
  **$4M**. The pre-score replaces the thin-gapper lottery with liquid names — the measured
  real-EP profile (ADV$ AUC 0.72 vs gap's 0.34).
- **The 26-winner labelled set on its own days** (real-ADV basis everywhere):
  UMC 04-17 gap 18 → pre-score 6 · AMD 04-24 15 → 2 · INTC 04-24 3 → 1 · QCOM 04-24 20 → 4 ·
  QURE 05-29 13 → 13 · APLD 04-08 14 → 15. **No member that gap admitted is dropped.**
  Members that stay out under both keys (AMKR 35, USAR 32, ALGM 59 on 04-08's flood board)
  match Stage 0's read: their ADV$ tier cannot beat 20+ mega-cap names on that morning.

## Data and provenance

- **One capture** (2026-08-22, read-only): `scripts/probes/_prescore_replay_capture.sql` →
  `_prescore_replay_{boards,themes,outcomes,board0408,outcomes0408,advfill}.psv` (q6 advfill
  pulled in the same session after the first replay run exposed the April ADV gap — see
  basis table below). Never re-run to re-read.
- **Replay code**: `scripts/ep_rubric_replay.py` — imports the LIVE
  `shortlist_prescore` / `shortlist_sort_key` / `SHORTLIST_SIZE` from `ep_rubric` (never a
  reimplementation), full output at `scripts/probes/_prescore_replay_out.txt`.
- **Boards**: `mi_ep_scan_log` last-seen state per (scan_date, ticker) — the house
  `get_ep_scan_log` idiom — minus `filter:universe_*` visibility rows (never candidates).
  91 logged days 2026-04-13 → 2026-08-21, plus the reconstructed 2026-04-08 open board
  (daily prints: open gap ≥ 9%, prev close ≥ $5, CS/ADRC, ticker ≤ 5 chars → 119 names;
  the scan log does not reach back to the day 13 of the 26 labelled EPs died).
- **ADV basis per day** (flagged per line in the output):

  | basis | days | ADV source |
  |---|---|---|
  | LIVE | 78 (2026-05-01 →) | the scan log's own `adv` column, 100% coverage |
  | ADVFILL | 13 (04-13 → 04-30) | bars-based 20-day mean volume (q6) — these rows predate the adv column; without the fill the pre-score degenerates to a flat-composite ticker-order lottery on exactly these days |
  | RECON | 1 (04-08) | bars-based, same recipe as the board reconstruction |

- **Theme membership**: `mi_themes` joined per day as the latest Accelerating/Mainstream
  snapshot ≤ scan_date within 7 days — the live `get_active_themes(stale_after_days=7)`
  predicate. Not proxied, not scored zero.
- **Outcomes**: computed from `mi_daily_closes` forward bars (5-day max high and 5th close vs
  the day-0 open). `mi_ep_missed_outcomes` deliberately NOT used — it is a 30-day rolling
  window and its stale-row class (#583) corrupted a prior ranking table.

## Result 1 — the labelled real EPs, day by day

| member (day) | gap rank | pre-score rank | gap top-20 | pre-score top-20 | in theme |
|---|---|---|---|---|---|
| SNDK 04-08 | 56 | **1** | out | **IN** | Y (AI Memory & Storage) |
| MU 04-08 | 64 | **3** | out | **IN** | n |
| BE 04-08 | 65 | **5** | out | **IN** | n |
| APLD 04-08 | 14 | 15 | in | in | n |
| QBTS 04-08 | 39 | 22 | out | out (boundary) | n |
| USAR 04-08 | 96 | 32 | out | out | n |
| AMKR 04-08 | 115 | 35 | out | out | n |
| ALGM 04-08 | 106 | 59 | out | out | n |
| UMC 04-17 | 18 | **6** | in | in | n |
| AMD 04-24 | 15 | **2** | in | in | n |
| INTC 04-24 | 3 | **1** | in | in | Y |
| QCOM 04-24 | 20 | **4** | in | in | n |
| ARM 05-06 | 100¹ | **3** | out¹ | **IN** | Y (Custom AI Silicon) |
| UMC 05-06 | 103¹ | 77 | out¹ | out¹ | n |
| SNOW 05-07 | 46¹ | **3** | out | **IN** | n |
| QURE 05-29 | 13 | 13 | in | in | n |
| MRNA 08-19 | 2 | 4 | in | in | n |

¹ Day-level (last-seen) ranks — the day's final gap read, not the alerting tick's. ARM and
UMC actually **beat the old cap at their ticks** (logged ranks 18/14; SNOW logged 22) and died
at the score — Stage 0's finding. The pre-score ranks are tick-stable (ADV$ is fixed the
night before), so their day-level read is the reliable column here; the gap column is not,
which is itself a point for the flip. UMC 05-06 ranks out under the pre-score on this
132-name day-level board where Stage 0's open-tick read had it 8–12 — the open board was
smaller; treat UMC 05-06 as boundary-sensitive, not cleanly recovered.

**Not coverable**: FLY 03-12, SMTC 03-30, AEHR/MRVL 03-31 (pre-scan-log, no reconstruction
attempted); ASX/HUT/IREN/NBIS/STRL 04-08 and TDIC 05-12 (below the 9% floor at the open /
absent from that day's log — floor kills, not cap kills; Stage 0 already classified them).

## Result 2 — what the shortlist trades away, honestly

Fwd 5-day outcomes of the swapped name-days (LIVE-basis era, 2026-05-01 →, n≈355/side):

| set | median max-high vs d0 open | ≥+20% | ≥+50% | median 5d close vs d0 open |
|---|---|---|---|---|
| ADDED by pre-score | +8.1% | 60 | 10 | −0.1% |
| DROPPED by pre-score | +12.0% | 118 | 34 | −0.4% |

- **The dropped set spikes harder** — thin max-gap names have fatter raw excursion tails.
  **The spikes do not hold**: by the 5-day close the two sets are equivalent (−0.4% vs −0.1%
  medians). Raw board-level excursion is also not tradeability — these names still face RVOL,
  extension, mcap, the score and the catalyst grade, which is where the 562b study showed the
  thin-spike class dies.
- **Historical HIGH alerts in the dropped set: 18 of 508 name-days.** 16 are April-era rows
  (old regime: 10% floor, 2.0× RVOL, old rubric — and two are USAX/USGG, the known
  ETF-admission mistakes later hard-filtered). In the current-era window only **2 of 16
  historical HIGHs lose their slot**: CRI 05-06 (+12.1% max-high, −3.9% close) and POWI
  05-26 (+12.3%, +6.3%) — ordinary gapper outcomes, neither labelled. The added set contains
  0 historical HIGHs by construction (never graded) and 8 historical MODERATEs.
- **Flood-day composition**: on 04-08 the pre-score's top 20 is index heavyweights + the
  liquid labelled set (the mega-cap flood #533 predicted — 13 names on that board carry max
  liquidity points); the tie-break (continuous ADV$) is what keeps that boundary deterministic
  instead of a 9-way lottery.

## Result 3 — the theme term is near-signal-free where it mattered most (as predicted)

On 2026-04-08 only 4 themes were Accelerating/Mainstream, covering **22 tickers, 4 of them on
the 119-name board** (vs 43 themes / 304 tickers on 08-20). The one board effect: SNDK's +10
(AI Memory & Storage) secures rank 1. **Any improvement the replay shows on 04-08 comes from
the liquidity axis, not the theme term.** Carried caveat: historical membership reflects the
theme engine's state at the time, including its known identity bugs (#553 false merges,
08-21 revalidation churn).

## ⚠ What this does NOT answer

- **Entries.** Nothing here says the recovered names alert or trade — Stage 0 priced that:
  under the day's regimes and the score/catalyst wall, at most SNOW converts, conditionally.
  This replay measures WHO GETS LOOKED AT, which is what the flip changes.
- **Per-tick truth.** The live cap acts per 5-minute tick; this replay ranks day-level
  (last-seen) boards. Gap ranks move intraday (ARM 18→100 within 05-06); pre-score ranks are
  tick-stable by construction, so the approximation biases AGAINST the gap key's look — the
  logged-tick ranks are quoted wherever they differ.
- **The April basis.** 13 days rank on bars-backfilled ADV (the adv column didn't exist);
  security-type filtering on the 04-08 reconstruction uses TODAY's `mi_security_types`.
- **Catalyst grades** for never-graded names (the added sets) — retro-grading costs LLM spend.
- **Whether the two lost current-era HIGHs (CRI, POWI) matter** — their outcomes were
  ordinary, but that is 2 samples, and the monitor (labelled EP falls out of the shortlist ·
  HIGH volume halves vs 30-day average · two silent days) is what watches this class live.

## Files

- This doc: `docs/analysis/shortlist_prescore_replay_2026-08-22.md`
- Replay: `scripts/ep_rubric_replay.py` → `scripts/probes/_prescore_replay_out.txt`
- Capture (one pull): `scripts/probes/_prescore_replay_capture.sql` + the six `.psv` files
- Anchors: `docs/analysis/shortlist_survival_stage0_2026-08-22.md` (Stage 0) ·
  `docs/analysis/real_ep_retention_562b_2026-08-22.md` (the 16-of-26 attribution) ·
  `tests/fixtures/must_not_miss_eps.py` (the labelled set) · `docs/setups/magna53_ep.md`
  change log 2026-08-22 (the flip + operator quote)
