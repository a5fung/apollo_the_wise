# Cross-strategy allocator (#31 / #44 / #312) — SHADOW

> SSoT for the unified allocator: what it ranks, when, against which book, what it writes, and
> the bar that decides whether its field is the right one. Registered in `docs/SSoT.md`
> 2026-10-10 (it had no owner before — `magna53_ep.md` lists it as OUT of that setup's scope and
> `safeguards.md` owns only the cap vocabulary it reads). Update THIS file in the same commit as
> any change to `agents/market_intelligence/cross_strategy_allocator.py`, its scheduler
> registration, or `db.get_open_position_count`. ⚖ THE LINE: it is SHADOW — it submits nothing
> and nothing on the money path reads it; a live rung (Phase 1B) needs his sign-off.

## What it is

- **Phase 1A, shadow, since 2026-05-08.** Ranks the day's queued MAGNA53 candidates on a
  0–100 composite (`0.40·setup + 0.30·catalyst + 0.20·volume + 0.10·regime`; tie-break
  `pm_rvol → gap_pct → strategy priority`) and names the top-`slots` as `winners`. The legacy
  first-come-first-served ORB entry path runs unchanged beside it.
- **Why it exists:** the 5/7 incident — 9M Day 2 took every free slot before the MAGNA53 ORB
  monitor at 09:31. 9M Day 2 is gone (#515, 2026-08-02); MAGNA53 is the only strategy that
  enqueues today, so the ranking is currently intra-strategy.
- **Phase 1B (active submission) is NOT built** and is gated by `data_gated_reviews.yaml`
  `unified_allocator_phase_1b` + PLAN #312 (the RED-3 clamp landed 7/13; this timing fix is the
  second pre-flip gate).

## When it runs, and against what

| | |
|---|---|
| Job | `scheduler._unified_allocator_shadow_job`, id `unified_allocator_shadow`, EXECUTION-owned (apollo-execution) |
| Time | **09:28 ET, Mon–Fri** (#312 Step A, 2026-10-10). 09:35 from 2026-05-08 to 2026-10-10. |
| Grace | `misfire_grace_time=90` s — a stalled loop may start it as late as 09:29:30, never at 09:30; past that it is SKIPPED + paged (#672) and the recovery sweep never re-runs it (it excludes every execution-owned id), so a miss can never re-run after the fills |
| Queue | `mi_pending_allocations` rows for `target_date` with `status='pending'`, written ONLY by `ep_detector → db.enqueue_pending_allocation` (HIGH + MODERATE tiers; `lane is None` — the small-cap paper lane never enqueues) on the EP scan that runs every 5 min from 07:00 ET. UPSERT: a re-score refreshes `composite_score`, `raw_dimensions` and `created_at` (so `created_at` is LAST write, not first arrival) |
| Book | `db.get_open_position_count(account_mode="live", before_alert_date=target_date)` = live rows in `db.OPEN_POSITION_STATUSES` whose `alert_date < target_date`. **The pre-entry book.** A row with `alert_date == target_date` is one of the day's entries (the ORB submit flips it `confirmed` at 09:31, #461) — it is being RANKED, so it must not also be COUNTED. Keyed on `alert_date`, not the clock, so a late run reads the same book. Live only: the lowcap paper lane's `account_mode='paper'` rows share `mi_live_trades` (#624) and carry no slot pressure |
| Slots | `max(0, MAX_CONCURRENT_LIVE_POSITIONS − book)` — the cap VALUE and the open-status vocabulary are `safeguards.md`'s; this file only says which rows the allocator counts |
| Writes | `shadow_rank`, `shadow_allocated`, `evaluated_at` on the queue rows (status stays `pending`); ONE `unified_allocation_decided` audit row |
| Submits | **nothing** |

### The audit row (`mi_audit_log.detail`, JSON text)

`target_date`, `regime`, `open_positions` (the pre-entry live book), `slots_available`,
**`ranked_at_et`** (ISO, ET-aware — the instant the queue was read), **`ranked_ids`** (the queue
row ids this ranking saw, in rank order), `n_candidates`, `n_winners`, `winners[]` and
`lower_ranked[]` (≤10) each with `rank / ticker / strategy / composite / legacy_eligible` (#415:
`eligible` = ep_score ≥ the regime HIGH bar; a deprecated strategy = `ineligible`; anything
else `unclassified`), `first_cascade_candidate` (#415, data only — cascade BEHAVIOUR is an open
operator fork). An empty queue writes `{target_date, n_candidates: 0, ranked_at_et, ranked_ids: []}`
— the same two stamps as a full row (18 of the last 31 mornings had an empty queue, so a row
without `ranked_ids` would read NULL to the Step B join and to the day-one check).
`ranked_at_et` + `ranked_ids` were added 2026-10-10 for the Step B bar below.

### Who reads it (verified 2026-10-10 — nothing on the money path)

`db.py` (the three queue functions), `cross_strategy_allocator.py`, `scheduler.py` (job +
registration), `ep_detector.py` (the enqueue), `audit_events.py` (the event-name constant),
`agent.py` (a lifecycle-display NOISE filter that DROPS this event), `data_gated_reviews.yaml`
(read-only review SQL). Nothing in `broker/`. `get_open_position_count` has one caller — this
module; the cap safeguard counts through `live_tracker.count_open_positions` (its own SQL).

## Findings this owner carries (what each ESTABLISHED)

- `docs/analysis/allocator_1b_comparison_2026-07-03.md` — on 26 contested days there was **no
  day where an allocator winner and a non-winner both traded through**, so "do the picks beat
  FCFS" was not decidable; §3(b) first recorded that `slots_available` is a point-in-time
  snapshot the legacy path does not share; §9.3 proposed reading slots live at each candidate's
  own attempt time (= Step B).
- `docs/analysis/unified_allocator_phase_1b_2026-09-14.md` — §2: the 09:35 ranking was taken
  AFTER the 09:31 entries, so **6 of the 7 winners that ever filled had already filled** and
  were counted twice; the recorded winners-vs-fills comparison was circular. §3: on 7 of 9
  contested days fewer names entered than there were slots — the setup filters, not the cap,
  decide these books. §5: the review predicate now counts only rows ranked `< 09:30 ET`
  (self-enforcing era scope — it read 0 until this move landed). §6: the +10 theme bonus is 40%
  of the ranking and changed the winner SET on 2 of 14 cap-bound days (one tradeable, +$19,
  N=1) — re-measure on post-move contested days, keyed on `score_breakdown.theme_bonus > 0`.
- **Prod read 2026-10-10** (`scripts/probes/_wk1010_312/`, read-only): last 45 days, 32 trading
  days, 38 queue rows on 18 dates — first seen by 09:28: 20 rows on 12 days; 09:28–09:35: 1
  (INTC 09-21); after 09:35: 17 rows that NO run has ever ranked. The queue is non-empty at
  09:28 on 12 of 32 days vs 13 of 31 at 09:35, so the move costs one row in 45 days; every one
  of the 15 live entries in the window was confirmed on its own `alert_date` at 09:31–09:36 ET.
- **The live-account filter fixes contamination that already happened** (prod read 2026-10-10,
  `scripts/probes/_wk1010_312/q4_fix_round.out`): the 2026-10-09 09:35 row read
  `open_positions=5, slots=0` with HUM (the only candidate) ranked below the cut — but only 3 live
  rows were open (KOD, PENG, and HUM itself, filled at 09:31). The other 2 were the #687 paper
  rehearsal's KO and PEP rows, deleted at 09:41. On the pre-entry live book (KOD, PENG) the same
  morning has `open_positions=2, slots=3` and HUM wins. The live safeguard was unaffected — it
  counts per account. **Baseline for the new reading:** of the 20 non-empty-queue mornings since
  08-12, the old 09:35 row's `open_positions` read ABOVE the rebuilt pre-entry book on 11 (worst:
  10-09, 5 vs 2), equal on 9, below on none.

## The ruling, and the bar for Step B (written before the data)

**Operator 2026-09-14: "aligned, A, then B if this becomes necessary" — SIGNED.**
A (this file's state) = rank at 09:28 against the pre-entry book. B = the July §9.3 design —
read slots live at each candidate's own attempt time, keeping the whole day's field.

**B is owed if, over 15 contested post-move days (`0 < slots_available < n_candidates`), the
names first enqueued AFTER the ranking would have outranked the 09:28 winners on more than a
third of those days. If they rarely outrank, A is sufficient and B is closed.**

How to measure it from the two tables alone: for each post-move audit row, the late arrivals
are that `target_date`'s `mi_pending_allocations` rows whose `id` is NOT in `ranked_ids`; a late
arrival "outranks" when its `composite_score` beats the lowest `composite` in `winners[]`
(ties by the tie-break key). `created_at` is last-write and must not be used for arrival;
`mi_ep_scan_log.scan_time_et` (first HIGH/MODERATE row) is the cross-check.

## Checking a morning live (`scripts/probes/_wk1010_312/q4_fix_round.sql` §F runs this over 60 days)

Rebuild the 09:28 book from timestamps and compare it to the audit row's `open_positions` for the
same `D` (the ET date). **Never** count by status at check time — a position that closed after
09:28 is no longer `filled`, so that count reads low (on the 42 audit days since 08-12 it read
below the rebuilt book on 41, and 0 against a true 2–4 on 33).

```sql
SELECT COUNT(*) FROM mi_live_trades
WHERE account_mode = 'live' AND alert_date < D
  AND confirmed_at < (D + TIME '09:28') AT TIME ZONE 'America/New_York'
  AND (closed_at IS NULL OR closed_at >= (D + TIME '09:28') AT TIME ZONE 'America/New_York')
  AND status NOT IN ('cancelled', 'skipped');
```

- **Proves:** the count is the live pre-entry book — a paper row open at 09:28 is not in it
  (the old code read it +N), and a position that closed after 09:28 still is.
- **Does NOT prove the `alert_date <` cutoff.** At 09:28 no same-day row exists yet (all 15 live
  rows of the last 45 days were created 09:31–09:36), so the cutoff changes nothing on a normal
  morning (the 90 s grace keeps even a late run before 09:30);
  a build that dropped it would read the same here. Only
  `test_slots_come_from_the_pre_entry_live_book_not_the_live_count` pins it — it bites on a run
  after the 09:31 entries (a manual re-run, a widened grace).
- **The stamp proves ordering:** `ranked_at_et` earlier than the day's first live `confirmed_at`
  (09:31) is the check that the job ran before the entries.

## Change log (newest first)

### 2026-10-10 — #312 Step A: 09:35 → 09:28 ET, and the book is the PRE-ENTRY live book (operator-signed 2026-09-14)
**What changed:** cron `minute=35 → 28` + `misfire_grace_time=90`; `db.get_open_position_count`
gained two parameter-bound filters (`account_mode`, `before_alert_date`; unfiltered call
unchanged) and the allocator passes `("live", target_date)`; the audit row gained `ranked_at_et`
+ `ranked_ids`. **Why:** the 09-14 §2 double count — a timing artifact, not a sizing defect.
**Unchanged (THE LINE):** cap value, open-status vocabulary, every entry/skip/fill path; the job
still submits nothing. **Tests:** `tests/test_allocator_legacy_eligibility.py` (slot math with
the morning's fills present — fails on the 09:35 code; the registered cron + grace bound; the
bound query parameters; the audit fields incl. `ranked_ids: []` on an empty queue). **Known cost, signed:** rows first enqueued after
09:28 (the 09:31 `ep_scan_open` upgrades) are not ranked — the Step B bar above decides whether
that matters. Probe files: `scripts/probes/_wk1010_312/`.

### 2026-08-02 — #515: `score_9m_day2` and the 9M Day 2 enqueue removed; MAGNA53 is the only writer.
### 2026-07-24 — #415: `legacy_eligible` + `first_cascade_candidate` added to the audit row; deprecated strategies barred at enqueue (#424).
### 2026-05-08 — Phase 1A shadow ship (#31), 09:35 ET.
