# Unified Allocator Phase 1B (#44) — comparison study for the Saturday promotion decision

**Status: evidence prepared, read-only, no code/config changed.** This is the "Saturday Sonnet
card" flagged as outstanding in `docs/analysis/datareview_evidence_pack_2026-07-04.md` item 3.
Prepared 2026-07-03 PT. Source: `data_gated_reviews.yaml` review `unified_allocator_phase_1b`
(line ~1161), full block read before starting, including the 5/18 deferred-evaluation ledger.

## 1. Predicate check

```sql
SELECT COUNT(DISTINCT date_trunc('day', created_at AT TIME ZONE 'America/New_York'))
FROM mi_audit_log
WHERE event_type = 'unified_allocation_decided'
  AND created_at > NOW() - INTERVAL '30 days';
```
Returns **20** (threshold 15) — predicate satisfied.

To maximize N for the actual comparison, this study pulls the **full history since the 5/8
deploy** (5/11 through 7/2, 37 event rows, 34 with a non-empty candidate queue), not just the
trailing 14 or 30 days the predicate/action SQL default to. This is a superset and still clears
the gate.

## 2. Method

```sql
-- Full event pull
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS day, summary, detail
FROM mi_audit_log
WHERE event_type = 'unified_allocation_decided'
ORDER BY created_at;

-- Flatten winners + lower_ranked out of the JSON, join to actual entry-pipeline outcomes
WITH events AS (
  SELECT (detail::jsonb) AS d
  FROM mi_audit_log
  WHERE event_type = 'unified_allocation_decided'
),
candidates AS (
  SELECT (d->>'target_date')::date AS alert_date,
         (d->>'slots_available')::int AS slots,
         (d->>'n_candidates')::int AS n_candidates,
         w->>'ticker' AS ticker, w->>'strategy' AS strategy,
         (w->>'rank')::int AS rank, (w->>'composite')::numeric AS composite,
         'winner' AS role
  FROM events, jsonb_array_elements(COALESCE(d->'winners','[]'::jsonb)) AS w
  UNION ALL
  SELECT (d->>'target_date')::date, (d->>'slots_available')::int, (d->>'n_candidates')::int,
         w->>'ticker', w->>'strategy', (w->>'rank')::int, (w->>'composite')::numeric,
         'lower_ranked'
  FROM events, jsonb_array_elements(COALESCE(d->'lower_ranked','[]'::jsonb)) AS w
)
SELECT c.alert_date, c.rank, c.role, c.ticker, c.strategy, c.slots, c.n_candidates,
       t.status, t.skip_reason, t.total_pnl, t.entry_price, t.signal_type
FROM candidates c
LEFT JOIN mi_live_trades t ON t.ticker = c.ticker AND t.alert_date = c.alert_date
ORDER BY c.alert_date, c.rank;
```

**Contested day** = `n_candidates > slots` (the review's own definition — a day where the
allocator's ranking could actually have changed who gets a slot vs an FCFS/legacy order).
**Traded-through** = `mi_live_trades.status = 'closed'` (a real fill with a realized `total_pnl`;
`status IN ('skipped','cancelled')` or no row at all = intercepted downstream, per the 5/18
deferral's own exclusion rule — these don't count toward the comparison).

Per contested day, classify:
- **agreement** — the allocator's winner traded through and no non-winner did (the real-world
  FCFS outcome and the allocator's pick coincide; today's actual result IS what the allocator
  wanted).
- **FCFS-only** — the allocator's winner did NOT trade through, but one or more non-winners
  (candidates the allocator ranked below the cutoff) DID — this is the direct analog of the
  5/18 ledger's CSCO/KLAR finding. Net P&L of those trades tells us whether the allocator's
  implicit exclusion looks right in hindsight.
- **both-traded** — winner AND a non-winner both traded the same day — a genuine head-to-head.
- **indeterminate** — nothing traded through at all (allocator's winner(s) intercepted, and no
  non-winner reached a fill either).

## 3. Structural findings that bound what this data can show (read before the tally)

**(a) The allocator's candidate pool is broader than the legacy auto-entry-eligible pool.**
`ep_detector.py` enqueues both HIGH *and* MODERATE tier MAGNA53 candidates into
`mi_pending_allocations` for scoring (only HIGH auto-submits under the legacy path — MODERATE
goes to the morning briefing only). `scheduler.py`'s 9M Day-2 job similarly enqueues *every*
pending sugar baby, while the unchanged legacy "Path C" logic only submits the top-N sorted by
its own quality metric within leftover slots. Net effect: a large fraction of `lower_ranked`
(and even some `winners`) were never real auto-entry candidates under the system as it runs
today, regardless of what the allocator decided — they show up as "no row" in `mi_live_trades`
(60 of 121 contested-day non-winner records; 3 of 16 contested-day winner records). A day can
look "contested" by the allocator's own `n_candidates > slots` count while containing zero
candidates that could ever have traded through either mechanism.

**(b) `slots_available` is a single point-in-time snapshot, not the same figure the legacy path
sees intraday.** 2026-05-11: the allocator computed `slots_available=0` (7 open positions ≥ cap)
and picked zero winners — yet three legacy (FCFS) trades (BW, MRAM, MNDY) entered and closed
that same `alert_date`. Positions open/close throughout the day; the allocator's one-time read
at its cron tick does not track that. This means "contested because slots=0" sometimes reflects
stale/mismatched slot accounting rather than a real capacity constraint the legacy path also
faced.

**(c) `9m_day2` was demoted `paper → shadow` on 2026-06-18 15:09 UTC** (`mi_audit_log`
`strategy_phase_change`: "9m_day2 demoted paper → shadow"). From that point on, every 9m_day2
candidate is blocked pre-submission (`block:strategy_in_shadow`) independent of the allocator —
it cannot appear as a real FCFS trade at all. Of the 34 non-empty decision days, **8 postdate
the flip** (6/18, 6/22, 6/24, 6/25, 6/26, 6/29, 6/30, 7/2); of the 26 contested days, **8 are
post-flip and involve 9m_day2 candidates that were structurally un-tradeable**, contributing
zero comparison signal. The effective two-strategy comparison window is really **5/11–6/17 (18
contested days)**, not the full 26 the day-count implies.

## 4. Per-day evidence

`[9m-shadow]` = date is on/after the 6/18 9m_day2 shadow-demotion.

| Date | Slots | N | Winners (ticker:disposition) | Non-winners traded (ticker:P&L) | Class |
|---|---|---|---|---|---|
| 2026-05-11 | 0 | 12 | (none) | BW:$2492; MRAM:$-2200; MNDY:$-1014 | FCFS-only (net -$721) |
| 2026-05-12 | 1 | 14 | ZBRA:skipped | - | indeterminate |
| 2026-05-13 | 2 | 3 | AIP:skipped; EOSE:unfilled | - | indeterminate |
| 2026-05-14 | 1 | 16 | VSNT:skipped | CSCO:$-406; KLAR:$-914 | FCFS-only (net -$1,321) |
| 2026-05-15 | 1 | 6 | GEMI:unfilled | KLAR:$-854 | FCFS-only (net -$854) |
| 2026-05-18 | 3 | 1 | SEDG:skipped | - | not-contested |
| 2026-05-19 | 3 | 5 | TE:skipped; STUB:skipped; AGYS:unfilled | - | indeterminate |
| 2026-05-20 | 3 | 1 | PURR:TRADED($3) | - | not-contested |
| 2026-05-21 | 0 | 6 | (none) | RLAY:$-643; ROIV:$-862 | FCFS-only (net -$1,505) |
| 2026-05-22 | 0 | 3 | (none) | IBM:$396 | FCFS-only (net +$396) |
| 2026-05-26 | 0 | 6 | (none) | - | indeterminate |
| 2026-05-27 | 0 | 4 | (none) | CRSR:$1391; DY:$-438 | FCFS-only (net +$953) |
| 2026-05-28 | 1 | 6 | QTTB:no-row | RCAT:$1166 | FCFS-only (net +$1,166) |
| 2026-05-29 | 1 | 6 | DELL:TRADED($-272) | - | agreement |
| 2026-06-01 | 0 | 8 | (none) | FPS:$160 | FCFS-only (net +$160) |
| 2026-06-02 | 0 | 6 | (none) | - | indeterminate |
| 2026-06-03 | 0 | 4 | (none) | NVTS:$-830 | FCFS-only (net -$830) |
| 2026-06-05 | 0 | 3 | (none) | - | indeterminate |
| 2026-06-08 | 1 | 1 | NRIX:TRADED($-378) | - | not-contested |
| 2026-06-09 | 3 | 2 | GLXY:skipped; TNGX:skipped | - | not-contested |
| 2026-06-10 | 3 | 3 | PAYO:skipped; VELO:skipped; GLXY:TRADED($-363) | - | not-contested |
| 2026-06-11 | 1 | 4 | NAVN:TRADED($-319) | - | agreement |
| 2026-06-12 | 2 | 6 | VELO:no-row; SHAZ:unfilled | - | indeterminate |
| 2026-06-15 | 4 | 1 | ROKU:skipped | - | not-contested |
| 2026-06-16 | 2 | 2 | NTLA:unfilled; RXT:unfilled | - | not-contested |
| 2026-06-17 | 2 | 2 | QURE:TRADED($216); LION:unfilled | - | not-contested |
| 2026-06-18 [9m-shadow] | 1 | 4 | QURE:skipped | - | indeterminate |
| 2026-06-22 [9m-shadow] | 0 | 3 | (none) | SYRE:$-1483 | FCFS-only (net -$1,483) |
| 2026-06-24 [9m-shadow] | 1 | 5 | BLZE:no-row | - | indeterminate |
| 2026-06-25 [9m-shadow] | 0 | 2 | (none) | - | indeterminate |
| 2026-06-26 [9m-shadow] | 0 | 1 | (none) | - | indeterminate |
| 2026-06-29 [9m-shadow] | 0 | 10 | (none) | - | indeterminate |
| 2026-06-30 [9m-shadow] | 0 | 2 | (none) | - | indeterminate |
| 2026-07-02 [9m-shadow] | 1 | 2 | DLO:skipped | - | indeterminate |

(6/4 and 6/23 and 7/1 are empty-queue days, excluded — 0 candidates.)

## 5. Tally

| Category | Days |
|---|---|
| Total non-empty decision days | 34 |
| Contested (n_candidates > slots) | 26 |
| Not-contested (everyone fit; trivial) | 8 |
| — of contested, **agreement** (winner traded, nothing else did) | 2 |
| — of contested, **FCFS-only** (a non-winner traded, winner did not) | 10 |
| — of contested, **both-traded** (real head-to-head) | **0** |
| — of contested, **indeterminate** (nothing traded through) | 14 |

Record-level (not day-level), contested days only:
| Population | Total records | Traded through | Skipped | Unfilled/cancelled | Still open (pending) | No row |
|---|---|---|---|---|---|---|
| Allocator **winners** | 16 | **2 (12.5%)** | 7 | 4 | 0 | 3 |
| Allocator **non-winners** (lower_ranked) | 121 | **15 (12.4%)** | 24 | 18 | 4 | 60 |

("Still open" = ABSI/FCEL 6/24, SNX 6/25, ACAD 6/26 — `status='pending_confirmation'` as of this
pull; no realized outcome yet, excluded from the P&L tally below.)

- Allocator winners that traded through: **DELL 5/29 (-$272), NAVN 6/11 (-$319) — 0 wins / 2
  losses.**
- Non-winners that traded through anyway (FCFS let them in despite the allocator ranking them
  out): **5 wins / 10 losses, net -$4,040** — BW +$2,492, IBM +$396, CRSR +$1,391, RCAT +$1,166,
  FPS +$160 (wins); MRAM -$2,200, MNDY -$1,014, CSCO -$406, KLAR -$914, KLAR -$854, RLAY -$643,
  ROIV -$862, DY -$438, NVTS -$830, SYRE -$1,483 (losses).

**There is no day in the dataset where the allocator's designated winner AND a different
non-winner both traded through on the same day** — the one comparison the review's question is
actually asking for ("do allocator picks beat FCFS picks", head-to-head) never occurs. Every
observed divergence is "FCFS traded something, the allocator's pick didn't trade at all" —
which tests the allocator's *exclusion* judgment (was the ticker it screened out actually bad?),
not its *selection* judgment against a live alternative.

## 6. Supplementary: forward returns on intercepted MAGNA53 winners

`mi_ep_scan_outcomes` (MAGNA53-only; no 9m_day2 coverage) gives raw price fwd-returns —
not risk-managed trade P&L, but a directional check on whether the allocator's picks that never
reached a real fill were, in hindsight, good calls:

| Ticker | Scan date | fwd_5d% | fwd_10d% |
|---|---|---|---|
| ZBRA | 5/12 | +8.97 | +8.97 |
| AIP | 5/13 | +8.21 | +8.21 |
| EOSE | 5/13 | +2.66 | +12.56 |
| AGYS | 5/19 | +4.21 | +18.84 |
| SHAZ | 6/12 | +56.42 | +56.42 |
| RXT | 6/16 | +38.49 | +38.49 |

All six intercepted MAGNA53 winners with `mi_ep_scan_outcomes` coverage moved up, several
sharply. This suggests the composite ranking itself was picking real strength — the "losses" in
the traded-through tally trace to downstream execution mechanics (stop-too-wide, ORB-unfilled,
fade guard, account/infra errors) rather than to the ranking logic choosing bad tickers. That is
a different axis from what this review is chartered to evaluate (ranking quality vs FCFS), but
it's directly relevant context for the operator.

## 7. Acceptance criteria, checked against the review's own text

> "do the ... audit events show the allocator's picks consistently match or beat the cron-order
> FCFS winners?"

**Not decidable either way from this data.** No day provides the head-to-head this phrasing
calls for (section 5). The closest available proxies are mixed: allocator winners that did
trade lost 2-for-2 (N too small to mean anything); FCFS-admitted rejects were net-negative
(5 W / 10 L, -$4,040) but a third of them were profitable, including one large winner (BW
+$2,492) the allocator would have excluded. Neither "consistently beats" nor "consistently
worse" is supported.

> "Validation criteria: on contested days, allocator winners include the score-96 /
> cap-saturated MAGNA53 names that 5/7 incident left blocked."

**Untested, not failed.** The two candidates matching that profile (HPE, composite 97.08,
6/2; MLTX, composite 98.4, 6/22) both occurred on days where the allocator itself computed
`slots_available=0` from carryover positions — it excluded them too, same as FCFS would have. No
day in this dataset presents a MAGNA53 HIGH candidate genuinely losing a scarce-but-nonzero slot
to a lower-quality 9m_day2 candidate (the 5/7 incident pattern) for the allocator to correct.

> (5/18 deferral) "Need ≥10 more days of telemetry where allocator picks actually trade through
> to outcomes."

**Partially addressed, still thin.** Days with at least one real traded-through outcome rose
from ~1/6 (5/18 ledger) to 12/26 contested days (46%) in this larger pull. But allocator-winner
traded-through volume specifically is still N=2. And 8 of the 26 contested days (31%) postdate
the 6/18 9m_day2 shadow-demotion and contribute no comparison signal at all — the "20
decided-days" that clears the predicate's day-count includes calendar time that cannot answer
the question, because half the competing strategies stopped being able to trade during it.

## 8. Caveats

- **N is small everywhere it matters.** 2 allocator-winner trades, 15 non-winner trades, 0
  head-to-head days.
- **9m_day2 in shadow since 6/18** removes one of the two strategies from the comparison for the
  most recent ~2 weeks of the window (out of scope for this review to investigate why; noted for
  the operator).
- **The allocator's candidate pool ≠ the legacy auto-entry-eligible pool** (MODERATE-tier MAGNA53
  + excess-quality 9m_day2 sugar babies were never real FCFS contenders regardless of ranking) —
  inflates "contested" day counts without adding comparison-relevant candidates.
- **`slots_available` is a stale snapshot** vs the legacy path's dynamic, intraday view of open
  capacity (5/11 example) — some "0 slots" days aren't real capacity constraints on the legacy
  side.
- **Interception rate is very high on both sides (~87.5% winners, ~87.6% non-winners never
  reach a fill)** — the dominant signal in the data is execution-mechanics attrition
  (stop-too-wide / faded / ORB-unfilled / infra), not allocator-vs-FCFS selection quality.

## 9. If more evidence is wanted

The smallest telemetry addition that would make this decidable directly, rather than by proxy:
1. When a winner is intercepted downstream (skip/cancel), have the entry pipeline check whether
   the **next-ranked candidate** from the same day's allocator ranking would also have been
   attempted under a real Phase-1B gate (cascade-or-not is itself an open design question — see
   §7's note that the current action_when_ready plan has no stated cascade behavior on
   downstream rejection of the #1 pick).
2. Log, per candidate, whether it was ever legacy-auto-entry-eligible (HIGH tier / within the
   legacy top-N) independent of the allocator's rank — so future day counts filter to only real
   contests instead of counting MODERATE/excess candidates that never had a chance either way.
3. Snapshot `slots_available` at the same cadence the legacy path checks capacity (or read it
   live at each candidate's own attempt time) instead of once at the 9:35 cron tick.

## Summary (neutral — operator decides)

The predicate (20 ≥ 15 decided-days) is met on a raw count. The underlying comparison the review
asks for — does the allocator's ranking beat FCFS on traded-through outcomes — **cannot be
directly tested** with the telemetry as currently shaped: zero days provide a genuine
same-day head-to-head, the allocator-winner traded-through sample is N=2 (both losses), the
non-winner sample is N=15 (net negative, but a third were winners including one large gain), the
named score-96-MAGNA53 validation scenario never occurred, and roughly a third of the contested
days postdate the 9m_day2 shadow-demotion and add no signal. Supplementary (non-P&L) forward-
return data on the intercepted MAGNA53 winners is directionally positive across all six covered
cases, suggesting the ranking logic itself may be sound even where this tally reads as a loss.
