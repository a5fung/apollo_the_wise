# The cross-strategy allocator cannot be validated against its own audit rows — it runs four minutes after the entries it is supposed to be choosing between

**2026-09-14 (PT) · $0 · prod read-only · no LLM in any classification · review `unified_allocator_phase_1b` (#44)**

## 0 — The bars, declared before the queries

The review entry's own criteria, quoted:

- *"on contested days, allocator winners include the score-96 / cap-saturated MAGNA53 names that 5/7
  incident left blocked"*
- *"compare the audit's `winners` array vs actual `mi_live_trades` fills for that alert_date"*
- threshold: 15 distinct days carrying `unified_allocation_decided` in 30 days.

⚠ **Before running either comparison I asked the question this repo's 2026-09-13/14 failures were
made of: what does the system ALREADY do on that date?** That question is what produced the finding
below, and it is the reason the two bars above cannot be scored as written.
[[check-what-the-system-already-did]]

## Population — which rows, over what window, and how it was derived

**Window:** `NOW() - INTERVAL '45 days'` → 2026-09-14, i.e. **2026-08-03 … 2026-09-14**. Chosen to
cover the review's own 30-day predicate window with margin, and to sit entirely after #415 shipped
(2026-07-24), which is what added `legacy_eligible` and the cascade fields the day-classification
uses. Nothing before that date is mixed in.

**Rows (two tables, no sampling — every row in the window is used):**

| population | source | n |
|---|---|---|
| allocator decisions | `mi_audit_log` where `event_type = 'unified_allocation_decided'` | **30 day-rows** |
| … of which carry a ranking (`slots_available` present) | the 11 empty-queue rows are excluded here and counted separately in §1 | **19** |
| … of which are CONTESTED (`0 < slots_available < n_candidates`) | the classification used everywhere below | **9** |
| entry attempts | `mi_live_trades` where `alert_date > today_ET − 45` | **82 rows**, live account only |
| contested-day candidates (winners + `lower_ranked`) joined to those rows on `(alert_date, ticker)` | | **39** |

**How each derived figure was built, so it can be checked rather than trusted:**

- **"Entered"** = `filled_at IS NOT NULL`. Deliberately NOT `status IN ('filled','closed')`: four rows
  carry `status='closed'` alongside `skip_reason='block:r3_reentry_disabled'`, and inspection of
  `filled_at` confirms those DID enter — the skip is a later re-entry block, not an entry block.
  Reading the status alone would have undercounted entries by four.
- **Fill times** are `filled_at` converted UTC → ET at a fixed −4h (the whole window is EDT; no DST
  boundary falls inside it) and compared against the 9:35 ET cron tick.
- **"Winner already filled"** compares that ET fill time to 09:35:00 — the job's registered trigger
  (`scheduler.py:7688`), not an assumed time.
- **Denominators** are stated at every percentage below. The 26% trade-through is 5 of 19 *winner
  slots on contested days*, not 5 of all winners ever.

⚠ **`skipped` rows with no `mi_live_trades` row at all (7 of 39) are counted as "never entered" but
called out separately in §3**, because they mean the candidate never reached the entry pipeline —
a different fact from being rejected by it, and the 2026-07-03 doc's §3(a) shows that gap is large.

## 1 — The predicate says READY on a count that includes days the allocator decided nothing — ⚠ AND THIS WAS ALREADY KNOWN

`SELECT COUNT(DISTINCT day) ... WHERE event_type='unified_allocation_decided'` = **20**, threshold 15.

🔴 **I did not find this. It was found on 2026-08-06 and written into this very entry**:
*"the predicate fires on ANY decision day (22 of 30), but the operator's 7/4 disposition requires
GENUINELY CONTESTED days, and measured with that honest condition the count is ZERO. The gate is
counting the wrong thing."* **The response was `regate_kind: date` — `earliest_review_date` pushed to
2026-09-01. The predicate itself was never touched, so it re-ripened five weeks later on the same
wrong count.** A date push does not fix a predicate that counts the wrong thing; it only delays the
moment it misreports. §5 fixes the predicate instead.

But `run_shadow_allocation` emits the SAME event name on an empty queue
(`cross_strategy_allocator.py:241` — `"empty queue for <date>"`, `n_candidates: 0`):

| in the last 45 days | days |
|---|---|
| **EMPTY QUEUE — no candidates, nothing ranked** | **11** |
| cap-saturated (`slots=0`, allocator produced no winners) | 4 |
| uncontested (`slots >= candidates`, everybody fits) | 6 |
| **CONTESTED (`0 < slots < candidates`) — the only days a ranking can matter** | **9** |

So the gate is armed on 30 rows of which **9** carry a decision that could ever differ from
first-come-first-served. Same shape as the birth-gate bucket that restated its own definition: an
event that fires whether or not anything happened cannot count as evidence that something happened.

## 2 — The allocator observes the world AFTER the entries it would have chosen

⚠ **Half of this is also not new, and the prior half is nearly ten weeks old.**
`docs/analysis/allocator_1b_comparison_2026-07-03.md` §3(b) already recorded that
*"`slots_available` is a single point-in-time snapshot, not the same figure the legacy path sees
intraday"*, and its §9.3 already recommended reading slots *"live at each candidate's own attempt
time instead of once at the 9:35 cron tick."* Its summary already said the comparison **"cannot be
directly tested."** That doc framed it as a capacity-accounting MISMATCH.

**What is new here is the direction and the size of it:** the snapshot is not merely mismatched, it
is taken *downstream of the fills*, so the allocator names winners that have already entered — and
that is quantified below for the first time. The July recommendation was never implemented, which is
why the same telemetry is being offered as evidence again today.

`scheduler.py:7688` runs the job at **9:35 ET**. Its own comment says so — *"Runs at 9:35 ET (after
MAGNA53 ORB monitor + 9M Day 2 cron have populated `mi_pending_allocations`)… Phase 1B (active) will
move this to 9:28 ET pre-market."* **ORB entries submit at 9:31.**

And slots are computed live at that moment, not from a 9:30 snapshot
(`cross_strategy_allocator.py:252`):

```python
open_count = await db.get_open_position_count()
slots = max(0, MAX_CONCURRENT_LIVE_POSITIONS - (open_count or 0))
winners = ranked[:slots]
```

**Of the 7 allocator winners that ever reached a fill in this window, 6 had ALREADY FILLED when the
job ran:**

| day | winner | filled (ET) | `open_positions` seen at 9:35 | `slots_available` |
|---|---|---|---|---|
| 2026-08-10 | ABCL | 09:34:33 | 2 | 3 |
| 2026-08-11 | BW | 09:31:49 | 3 | 2 |
| 2026-08-14 | ETON | 09:31:02 | 3 | 2 |
| 2026-08-18 | AMLX | 09:32:03 | 3 | 2 |
| 2026-09-08 | PHVS | 09:31:14 | 4 | 1 |
| 2026-09-14 | DFTX | 09:33:18 | 4 | 1 |
| 2026-08-27 | OKTA | **09:49:50** | 4 | 1 | ← the only winner that filled after the ranking existed

**Each of those six is counted twice** — once inside `open_positions`, where it consumes a slot, and
again as the winner of the slots that remain. On 2026-09-14 the book was OKTA/HOOD/SEI plus DFTX
filled at 09:33; the allocator read `open_positions=4`, offered `slots=1`, and named **DFTX** the
winner of it.

**Consequences, in order of how much they cost:**

1. **The review's comparison is circular.** "Do the allocator's winners match the actual fills" is
   guaranteed agreement when the winners are drawn from names that had already filled. Four months of
   telemetry cannot answer the question it was collected for.
2. **A live flip on this ranking would over-allocate**, because `winners` is sized against a slot
   count that already excludes some of the winners.
3. **Step 1 of the entry's own `action_when_ready` ("move shadow cron 9:35 → 9:28 ET") is not step 1
   of a promotion — it is a PRECONDITION of measuring anything at all.**

## 3 — And the cap it rations is almost never the binding constraint

Across the 9 contested days: **39 candidates, 19 slots offered, 8 ever entered — 21%.**

| why the other 31 never entered | n |
|---|---|
| `setup:gap_below_floor` | 8 |
| never reached the pipeline (no `mi_live_trades` row at all) | 7 |
| `block:circuit_breaker` | 5 |
| `setup:stop_too_wide` | 5 |
| ORB window unfilled | 2 |
| `broker:entry_rejected` · `setup:size_too_small` · `setup:chase_cap_exceeded` · `infra:no_bar` | 1 each |

On **7 of the 9** contested days, fewer names entered than there were slots. The 5-position cap did
not decide those books — the setup filters did. **Winner trade-through is 5 of 19 (26%)**, which is
the SAME interception rate that deferred this review on 2026-05-18 (*"current rate ~1/6 days"*). Four
months of waiting did not move it, which is the evidence that **more days is not the fix.**

## 4 — Verdict and recommendation

⚖ **DEFER AGAIN — but not for more days, and that is the change from 2026-05-18.** The 2026-05-18
deferral said "need ≥10 more days". It got 4 months and the blocker is identical, because the
bottleneck was never sample size:

- the comparison is **structurally unavailable** until the job moves ahead of 9:31 (§2), and
- at 3 candidate divergences in 45 days, even a sound comparison needs **~7 months** to reach N=15.

**Recommended order — and only the first is mine to do. ⚠ Note that steps 1 and 2 have each been
recommended once before (2026-07-03 §9.3; 2026-08-06's regate note) and neither was done — this
review has now been deferred three times, twice by moving a date.**

1. **Fix the double-count and move the shadow job to 9:28 ET.** Ranking against a pre-entry book is
   what makes the telemetry mean anything; it stays shadow-only, submits nothing, and costs $0. ⛔ It
   still changes WHEN a money-path job reads the book, so it ships with the numbers and **his
   sign-off — THE LINE.**
2. **Re-arm the predicate on contested decision days, not event days** (exclude `n_candidates = 0`),
   and re-scope the era to post-move.
3. **Only then** ask the FCFS-vs-allocator question.

🔴 **Do NOT flip Phase 1B on the current evidence.** The one signal ever cited for allocator value —
the 5/14+5/15 KLAR entries, −$1,768 — still stands at N=2 and predates the exit rule, the R3 re-entry
block, and the chase cap. [[check-the-rule-era-before-comparing-to-actual]]

## What this does not answer

- **Whether the allocator's RANKING is any good.** Nothing here scores its ordering; the finding is
  that the recorded comparison cannot test it, not that it fails one.
- **Whether the 5-position cap is the right number.** §3 says the cap rarely binds on contested days;
  that is an observation about these 45 days, not a sizing recommendation. Sizing is his (THE LINE).
- **Whether the setup filters that intercept 74% of winners are correct.** They may be doing exactly
  their job. This read only establishes that they, not the allocator, decide these books.
- **What happens on a cap-saturated day.** All 4 such days produced zero winners by construction, so
  they carry no information about the allocator either way.
- **Paper-account behaviour.** Live only — `slots` is deliberately live-only (paper has no slot
  pressure), so paper is out of frame.

## 5 — The predicate, rewritten so it cannot repeat this

Replaces the decision-day count. Tested against prod 2026-09-14 before being written here:
**14 over 90 days on the contested condition alone, and 0 with the era clause** — so it is armed,
runs clean, and reads honestly today.

```sql
SELECT COUNT(DISTINCT (created_at AT TIME ZONE 'America/New_York')::date)
FROM mi_audit_log
WHERE event_type = 'unified_allocation_decided'
  AND created_at > NOW() - INTERVAL '180 days'
  AND (created_at AT TIME ZONE 'America/New_York')::time < TIME '09:30'   -- era: post-move only
  AND detail IS NOT NULL
  AND (detail::jsonb ->> 'slots_available') IS NOT NULL
  AND (detail::jsonb ->> 'slots_available')::int > 0
  AND (detail::jsonb ->> 'slots_available')::int
      < (detail::jsonb ->> 'n_candidates')::int;
```

**The time clause is the point.** The job fires at 9:35 today and would fire at 9:28 after the move,
so the predicate **counts zero until the precondition actually lands** and then counts only post-move
days — no calendar, no `earliest_review_date` push, and nobody has to remember to re-scope the era.
That is the structural answer to a review that has twice been deferred by moving a date.

## Reproduce

`mi_audit_log` where `event_type = 'unified_allocation_decided'` joined to `mi_live_trades` on
`(alert_date, ticker)`; fills converted UTC → ET and compared against the 9:35 cron. Working files
were session-local; every number above is recomputable from those two tables alone.
