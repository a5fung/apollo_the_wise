# #490b — The 137 faded-then-crossed names: is there a floor-timing rule worth having? (2026-08-18, MEASURE-ONLY)

**One sentence:** No rule reachable by our machinery captures this class's winners under the
current selector — 88% of the class crosses 10% inside the first 15 minutes (so the class IS
an opening-range phenomenon, not an afternoon one), but each of its three ≥8×ADR winners is
blocked by a DIFFERENT non-floor gate (ALOY the 60-day cooldown, BCAR the $500M mcap floor,
AMRC the 09:45 ORB window end), the zero-parameter high-water rule therefore adds **0 tail
winners per month so far** while nominating ~84 extra candidates/month whose tail rate
(1.6–1.9% so far) is no better than the book we already alert (2.0%), and no decision-time
feature separates the winners — including the operator's specific fear case: the near-floor
band (open gap ≥8%) holds **0 of the 3 winners**.

⚖ **THE LINE:** the gap floor is entry discipline. This doc measures; it proposes no
threshold and flips no toggle. The fork below is the operator's alone.
🔴 **Provisional per the GOAL-section rule:** measured on the population the current
selector + floors produce; any upstream selection change re-opens this read.
**Right-censoring is severe: every forward window is incomplete (winners at 12–13 of 20
sessions; class median 8–9). Every share below is a FLOOR. Clean re-read after 2026-09-15.**
Probe: `scripts/probes/_490b_faded_crossed_timing.py` (deterministic on captured TSVs —
reuses the #490 funnel captures + a one-time 2026-08-18 `mi_intraday_bars` capture,
`_490b_intraday_bars.tsv`, 121 of 137 ticker-days covered). $0, read-only.

## Pre-registration (written before any subgroup outcome was computed)

Honesty note: the three winner identities + open gaps were already published in
`docs/analysis/490_delayed_screen_cost_2026-08-18.md`, so full blindness was impossible;
every threshold below was fixed in the probe header before the grid was run, and ALL cells
are reported.

- **PRIMARY — "high-water floor":** qualify if any minute-bar high in 09:30–09:45 reaches
  ≥ prev_close × 1.10. Only existing constants (the 10% floor, the 09:45 ORB window end).
  **Zero free parameters** — the exact replacement of the current ~09:31 point-read with a
  window-max read.
- **Sensitivity grid (all reported):** cross-by boundary {09:35, 09:45*, 10:00, 10:30,
  12:00, close} × open-gap sub-floor {none*, ≥0, ≥3, ≥5, ≥8}. Anchors are pre-existing
  system constants: 0 = the gap-down rule, 3 = the 9M gap floor, 5 = half the EP floor,
  8 = the operator's "near it" ARGX neighborhood. No other thresholds were tested.
- **Separability features at ~09:45** (all knowable at decision time): open gap, position
  in the 09:30–09:45 range, cumulative volume vs 20-session mean (RVOL proxy),
  extension %, ADR%, prev close vs 20-session max close. Winner = tailx-so-far ≥ 8×ADR.

## 1. The class, characterised (n=137; intraday timing on 121)

- **Cross times are front-loaded, not scattered:** 64 crossed by 09:35, 43 more by 09:45
  (**107/121 = 88% inside the ORB window**), 11 in 09:45–10:00, 0 in 10:00–12:00, 3 after
  12:00. "Crossed at 14:30" is essentially nonexistent — these are names gapping +3–6%
  that surge through +10% within minutes of the bell.
- Open gaps: median +4.3% (P25 +2.6, P75 +6.4, P90 +8.1); only 10/137 opened down.
- The 16 without intraday bars are excluded from timing only; their outcomes remain in
  every class total (daily bars).

## 2. Outcomes, tail first (tailx = 20-session fwd max high vs EP-day close, own-ADR units; ALL floors)

| cohort (same dates, same censoring) | n | ≥8×ADR so far | P90 | med | fwd med |
|---|---|---|---|---|---|
| REACHABLE: crossed by 09:45 (primary rule, pre-gates) | 104 | 2 (1.9%) | 4.91× | 1.47× | 8/20 |
| REACHABLE + replayed mechanical gates | 64 | 1 (1.6%) | 4.92× | 1.53× | 8/20 |
| unreachable: crossed after 09:45 | 12 | 1 (8.3%) | 8.20× | 3.49× | 12/20 |
| whole class (from the #490 funnel) | 132 | 3 (2.3%) | 5.25× | 1.57× | 9/20 |
| **ALL live alerts 07-27..08-17 (computed fresh today)** | **100** | **2 (2.0%)** | 3.67× | 1.44× | 7/20 |

The reachable subset's tail rate **matches the book it would be added to** — the high-water
rule dilutes, it does not concentrate.

## 3. Reachability — where each winner actually died (the decisive table)

| winner | tailx so far | cross | reachable by ORB? | what actually blocked it |
|---|---|---|---|---|
| ALOY 07-29 | 9.8× (13/20) | 09:30 | YES, passes all mechanical gates | **60-day EP cooldown** (alerted 06-01, 58d prior) — floor timing never reaches it |
| BCAR 07-29 | 14.7× (13/20) | 09:33 | YES | **mcap $227M < $500M** — the known 08-16 small-cap anti-selectivity, not floor timing |
| AMRC 07-30 | 8.8× (12/20) | **09:49** | NO — 4 min past the ORB window | only a delayed-entry lane (§4a) reaches it; we alerted it 08-04 on a later move |

**Zero of the three is captured by any floor-timing change under the current selector.**
The nearest sub-8× reachable names are blocked the same way: EROC 07-30 (7.89×, 12/20 —
could still convert) was IN the delayed scan log at gap 11.1% and cut by the **top-20 gap
cap**; EROC 07-31 by top-20 + routine catalyst; QUAD 07-29 by top-20 + mcap; IESC 07-31 by
session-RVOL + premarket volume. And 78 of the 137 appeared in the delayed scan log later
the same day — for the majority, the screen SAW them and rejected them on the merits; the
floor's 09:31 point-read was not the binding constraint.

## 4. Separability at ~09:45 — NO (a real answer, not a shrug)

- AUC vs the class, 3 positives: open gap 0.47 · position-in-range 0.52 · ADR 0.50 —
  chance. RVOL-by-09:45 0.24 and extension 0.24 — **inverted** (winners were *quieter* and
  *less extended*). Distance below the 20-day high 0.09 — strongly inverted (winners sat
  at 49–68% of their 20-day max close vs class median 93%).
- Nothing knowable at 09:45 ranks the winners UP; the only strong-looking signals rank
  them DOWN, on 3 names — selecting for "beaten-down, quiet open" would invert the entire
  EP methodology on anecdote-grade evidence. **The winners are not separable at decision
  time with these features.**

## 5. Parameter sensitivity (all 30 pre-registered cells; winners caught / pool size)

| cross-by | none | ≥0 | ≥3 | ≥5 | ≥8 |
|---|---|---|---|---|---|
| 09:35 | 2/64 | 1/61 | 1/55 | 1/38 | **0/14** |
| **09:45*** | **2/107** | 1/100 | 1/78 | 1/48 | **0/14** |
| 10:00 | 3/118 | 2/109 | 2/84 | 2/51 | 0/14 |
| 10:30–close | 3/118–121 | 2 | 2 | 2 | 0 |

- **The near-floor band (≥8%) holds ZERO winners in every column** — the ARGX-shaped
  "it was almost at 10" intuition is, in this class, empty so far.
- The best cell (10:00 boundary × ≥5 floor: 2/51 = 3.9%) is the best of 30 correlated
  cells with 3 total positives — noise-grade, and its boundary is past the ORB window, so
  it describes a §4a delayed-entry lane, not a floor-timing fix. Flagged for the 09-15
  re-read, nothing more.

## 6. The prize, in the programme's currency (target ≈1 converted tail winner/month)

- **Floor-timing rule (high-water by 09:45), current selector: +0.0 tail winners/month**
  (0 in 0.76 months) — vs 2.6/month the alerted book already produces.
- Counting ALOY (i.e., ALSO waiving the 60-day cooldown — a separate, unrequested fork):
  +1.3/month, at the cost of ~84 extra gate-passing candidates/month before the
  catalyst/RVOL/top-20 gates, whose tail rate so far is no better than the existing book.
- The class ceiling with perfect hindsight and no gates at all: 3.9/month — but that pool
  is unreachable by construction (window, mcap, cooldown, rank cap).

## Scope of this negative — and what remains untested

1. **This read covers never-alerted crossers only.** The operator's live ARGX case
   (alerted 10.5%, read 9.5% at 09:31, skipped, closed +16% at ATH) is the
   **alerted-then-floor-blocked class — a different population this study cannot answer**;
   that is #559's 08-31 false-block split, still open.
2. Catalyst grade, RVOL pace and top-20 rank were not replayed ($0 limit) — they would
   shrink the added pool further (scan-log fates suggest heavily), never grow it.
3. **Censoring:** every window incomplete; EROC 07-30 sits at 7.89× with 8 sessions left.
   If it converts, its blocker was the top-20 rank cap — still not the floor. Clean
   re-read after 2026-09-15.
4. 16/137 lack intraday bars (timing only; outcomes included). Bar persistence may
   correlate with having been an EP candidate that day — a mild timing-coverage bias.
5. Per the GOAL rule: if selection changes materially (mcap floor, cooldown, rank cap,
   catalyst grading), this read expires and the probe re-runs in minutes at $0.

## The fork for the operator (one sentence)

The 10%-at-09:31 point-read is not what is costing us this class's winners — each died on
a different gate (cooldown / mcap / ORB window), the zero-parameter fix captures none of
them while nearly doubling the candidate book at the same-or-worse tail rate, and the
near-floor band he flagged holds zero winners so far — so the floor-timing fork can rest
until the 09-15 re-read, while the ARGX-shaped alerted-then-blocked class stays open
under #559.
