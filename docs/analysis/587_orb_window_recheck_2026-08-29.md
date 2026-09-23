# #587 recheck — the ORB-window "missed winners" on corrected data (2026-08-29)

**MEASUREMENT ONLY.** Re-runs `docs/analysis/orb_window_587_2026-08-23.md` against
`mi_ep_missed_outcomes.setup_at_open` (shipped 2026-08-29, see
`docs/analysis/595_missed_outcomes_anchor_2026-08-29.md`). Nothing changed. The 9:45 window is
still the operator's sole call; this only checks whether the original doc's numbers survive.

**Source:** one prod capture, `skip_category='window_missed'`, all rows in `mi_ep_missed_outcomes`
as of 2026-08-29 (n=40). Query + output: `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/587recheck.sql`
/ `587recheck_out.psv`. `ret_5d` / `max_high_5d` are 5-day return and maximum favourable excursion
measured from the **day-0 open**, carry **no stop**, and are **not R** — a live bracket would have
capped every loser at −1R. Never read a negative row here as a realized loss.

---

## 1. Raw blocked rows vs. real setups

| population | n | real setup (`setup_at_open = t`) | not a setup (`f`) | unsettled (no ret_5d yet) |
|---|---|---|---|---|
| **All-time `window_missed` rows** | 40 | 22 (55%) | 18 (45%) | 2 (CHRN, VEEV, alerted 08-27 — too recent to settle) |
| **The original doc's specific 25-name/60-day cohort** (2026-06-24 → 2026-08-22) | 25 | 13 (52%) | 12 (48%) | 0 (all now settled) |

Nearly half the original doc's headline cohort — 12 of 25 — never actually gapped ≥9% at the
open. That includes **BLZE**, one of the two names the doc's prose leaned on hardest.

## 2. Corrected winner count vs. the original claim

Using the anchor doc's own bar (`ret_5d ≥ 0.20`), across the full all-time `window_missed` table:

| | n |
|---|---|
| Claimed winners (`ret_5d ≥ 0.20`) | **6** |
| Of which never a setup at the open | **2** (ALOY, BLZE) |
| **Corrected winner count** | **4** |

This matches the anchor doc's `window_missed \| 6 \| 2 \| 33%` line exactly.

⚠ **n = 4 is too few to draw a conclusion.** Stated plainly, not stretched.

## 3. Real-setup cohort's forward outcomes (ret_5d, day-0-open basis, no stop)

| cohort | n settled | mean ret_5d | median ret_5d | up (>0) | down (≤0) |
|---|---|---|---|---|---|
| All-time `window_missed`, real setups only | 21 | +7.2% | +9.3% | 14 (67%) | 7 (33%) |
| Original 25-cohort, real setups only | 13 | +7.3% | +11.8% | 8 (62%) | 5 (38%) |

n=21 and n=13 both clear the ~10-row floor for a weak read; neither clears it for a strong one.
Direction (majority green, positive median) holds in both cuts — but see §4 for how much smaller
and shakier than claimed.

## 4. Does the original doc's own arithmetic still hold?

Checked against its exact 25-name, 2026-06-24→2026-08-22 cohort, all rows now settled:

| claim in the original doc | as originally stated (n=23, partly unsettled) | on all 25 now settled, **uncorrected** | on the **13 real setups only** |
|---|---|---|---|---|
| % green at 5 days | 70% (16/23) | 72% (18/25) | **62% (8/13)** |
| median 5d return | +8.6% | +8.6% | **+11.8%** |
| touched +20% within 5 days | 9 of 25 | 10 of 25 | **5 of 13** |
| "2 of the period's 4 biggest would-be winners" | BLZE +78% peak, TSAT +38% ret | — | **BLZE is fake (opened +6.7%, never a setup); TSAT is real** |

**Plainly: the direction survives, the magnitude of the base does not.** The rejected class is
still majority-green and still carries a positive median — that part of the original doc's claim
holds up on the real-setup subset. But the base it was built on shrinks by nearly half (25→13),
one of its two named marquee winners (BLZE, the bigger of the two: +78% peak / +40% close) turns
out to be exactly the same failure mode as the VEEE case in the anchor doc — a pre-market print
that faded below the 9% floor before the bell — and the all-time winner count the corrected data
actually supports (4) is too small to found a conclusion on by itself.

The original doc never recommended a window change — it explicitly left that to the operator
(Result 4 / "What this means" #4). That framing is unaffected: there is no live decision to
walk back, only a measurement to correct.

## 5. Surviving winners, named (the corrected all-time count = 4)

| ticker | date | open gap | ret_5d |
|---|---|---|---|
| TSAT | 2026-08-04 | +9.5% | +35.2% |
| DCTH | 2026-08-06 | +11.1% | +23.7% |
| ARX | 2026-05-14 | +10.9% | +22.3% |
| MTW | 2026-08-07 | +20.6% | +20.7% |

Killed by the correction (credited as winners, never real setups at the open):

| ticker | date | open gap | credited ret_5d |
|---|---|---|---|
| BLZE | 2026-07-31 | +6.7% | +39.7% (peak credited: +78.1%) |
| ALOY | 2026-06-01 | +2.5% | +50.9% |

Of the 4 survivors, only TSAT, DCTH, MTW fall inside the original doc's specific 25-name/60-day
cohort; ARX predates it (it's part of the broader all-time `window_missed` population, not the
60-day window the original doc analyzed in its Result 1–3 tables).

---

## What this does not answer

- **Whether these 4 (or 21, or 13) were actually tradeable at the moment we saw them.** The
  original doc's minute-bar tradability/chase-cap check (its Result 3) was not re-run here —
  it's a separate question from the open-gap correction and this task didn't re-pull minute bars.
- **The entered-vs-rejected comparison (the original's Result 2 "70% vs 32%").** The entered
  cohort wasn't touched — MAGNA53 entries fill at the ORB high by construction, so they don't
  carry the pre-market-fade problem this correction targets. Not re-derived here; flagged only.
- **Era scope.** The original's caveat that this edge belongs mostly to the pre-rebuild selection
  (2R-stop era n=2, selection-rebuild era n=0) is untouched by this correction and still applies.
- **Why the `mi_ep_missed_outcomes` `window_missed` population (n=40) doesn't 1:1 match
  `mi_live_trades`'s all-time count of 57 `window:out_of_orb` skips.** Not reconciled here — out
  of scope for this recheck; noted so it isn't silently assumed to be the same set.
- **Whether a different 9:45 cutoff would perform better.** Entry-window discipline is the
  operator's sole authority (THE LINE); no level is proposed here, same as the original.
