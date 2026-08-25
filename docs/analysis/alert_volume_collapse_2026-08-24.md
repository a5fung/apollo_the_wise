# Why the HIGH alert rate fell about 80% in two weeks (2026-08-24)

**MEASUREMENT ONLY. Nothing was changed. No rule, threshold, filter, toggle or trade state was
touched, and nothing here is a recommendation — any change it implies is the operator's fork
(THE LINE).**

## The answer in one line

**Both step-downs are the tape.** The supply of gapping stocks tripled into the first week of
August and has now come all the way back to where it sat in July; alerts tracked it up and back
down. What we are calling an 80% collapse is measured from a four-day spike, not from a baseline.
Every conversion rate inside our own funnel is currently **at or above** its July level, so we
are not cutting harder — there are simply far fewer names to cut.

## The question

HIGH EP alerts per trading day, verified against production:

```
07-30  7    08-04 10    08-10  4    08-17  1
07-31  6    08-05  8    08-11  4    08-18  1
08-03  2    08-06  8    08-12  6    08-19  3
            08-07 10    08-13  5    08-20  2
                        08-14  4    08-21  1
                                    08-24  0
```

Two apparent step-downs — around 08-10 (10/day → 4-5/day) and around 08-17 (4-5/day → 1-2/day).

## Data

- Three read-only production captures, pulled once and read many (cost rule), all under
  `scripts/probes/`:
  - `_alertdrop_capture.sql` → `_alertdrop_capture_out.psv` — the deduped scan log, alerts,
    regime, safeguard/toggle state, per-day audit-event counts, and market breadth from
    `mi_daily_closes`.
  - `_alertdrop_capture2.sql` → `_alertdrop_capture2_out.psv` — **every scan tick** for
    2026-07-06 → 2026-08-24 (13,755 rows). Needed because the deduped last state hides the
    funnel: a name that alerts at 9:31 is logged as "already scored earlier today" on every
    later tick, so its last row looks like a duplicate, not an alert.
  - `_alertdrop_capture3_out.psv` — the catalyst-lattice monitor's own alert row, container boot
    times, and every error/failure/rate-limit event since 08-05.
- Arithmetic: `_alertdrop_funnel.py`, `_alertdrop_composition.py`, `_alertdrop_decompose.py`.
- Every name is assigned to the **furthest stage it reached** across all of that day's ticks, and
  the kill reason is bucketed by `missed_outcomes._categorize_skip_reason` — the canonical
  categoriser, reused, not re-implemented. Raw reasons embed dollar figures and percentages, so
  grouping on the whole string would make every price its own bucket.
- "Names gapping ≥10%" is computed from `mi_daily_closes` at the scan's own universe floors
  (prior close ≥ $5, prior-day volume ≥ 50,000 shares). It is an **open-to-prior-close** measure,
  while the scan reads a live price at each tick, so it is a directional control on how much the
  tape was offering — not a row-for-row reconciliation.

## Result 1 — the scan never faltered

Before attributing anything to a gate, the scan itself had to be cleared. It is clean on every
trading day in the window: **38 scan ticks a day, first tick 07:00 ET, last tick 09:55 ET, no
missing ticks, no null timestamps.** The batch write that records candidates is fire-and-forget
and swallows its own failures, so a thinning scan was the one explanation that could have faked
every other finding. It did not happen.

## Result 2 — the supply of gapping stocks tripled, then came all the way back

Per trading day:

| period | stocks gapping ≥10% | candidates the scan saw | names scored | HIGH alerts |
|---|---|---|---|---|
| 07-06 → 07-24 (July baseline, 15 days) | 19.7 | 13.9 | 3.6 | **1.13** |
| 07-27 → 07-31 | 53.0 | 39.6 | 12.4 | **3.60** |
| 08-03 → 08-07 (the burst) | 46.2 | 44.0 | 19.2 | **7.20** |
| 08-10 → 08-14 | 30.4 | 22.6 | 10.8 | **4.60** |
| 08-17 → 08-21 | 21.8 | 15.6 | 4.6 | **1.60** |
| 08-24 | 19.0 | 9.0 | 2.0 | **0.00** |

The number of stocks gapping 10% or more went from about 20 a day in July, to about 50 a day in
the last week of July and the first week of August, and is now back to about 20. The candidates
our scan actually evaluated followed the same curve — 14 a day, then 44, then 16. **The alert
rate is a shadow of that curve.**

Weekly HIGH alert totals put the same point plainly: 9, 6, 6, 8, 1, 5, 5 for the first seven
weeks of June and July — then 18, **38**, 23, 8. The 38-alert week of 08-03 is four to six times
anything the system had produced since June. Last week's 8 is squarely inside the June-July
range.

## Result 3 — the first step-down (08-10): alerts fell LESS than the supply did

Comparing the burst week (08-03 → 08-07) to the week after (08-10 → 08-14):

- Stocks gapping ≥10%: 46.2/day → 30.4/day (**−34%**).
- Candidates the scan saw: 44.0/day → 22.6/day (**−49%**).
- HIGH alerts: 7.20/day → 4.60/day (**−36%**).
- Share of candidates that became a HIGH alert: 16.4% → **20.4%** — it went **up**.

**Candidates fell by half and alerts fell by only a third.** A step caused by us cutting harder
looks like the opposite — alerts falling faster than supply. Here the funnel absorbed part of the
supply loss instead of amplifying it. Nothing tightened. In fact one thing loosened by itself:
on flood mornings the scan only grades the top 20 candidates a tick, and in
the burst week that cap discarded 15 names a day before any filter or grader saw them. From 08-10
onward the board never reached 20, so the cap stopped binding entirely and **every** candidate
was graded. That is why conversion improved.

## Result 4 — the second step-down (08-17) is mostly fewer names, and the rest is not us cutting harder

Week over week this one looks worse: candidates fell 31% (22.6 → 15.6/day) but alerts fell 65%
(4.60 → 1.60/day), so the share of candidates alerting halved, 20.4% → 10.3%.

Measured against July instead of against the burst, that halving disappears:

| stage | July baseline | 08-17 → 08-21 |
|---|---|---|
| candidates that survive to being scored | 26.0% | **29.5%** |
| candidates that become a HIGH alert | 8.2% | **10.3%** |
| scored names that clear the alert bar | 31.5% | **34.8%** |

**All three conversion stages are running better than they did in July.** The weeks of 08-03 and
08-10 were the anomaly — elevated on both supply *and* conversion — and last week is back inside
the normal range on every stage. There is no stage whose kill rate rose above where it has sat
all summer.

Where the week-over-week conversion dip does come from, in absolute names per day:

- **The names now arriving are cheaper and thinner.** Median prior close of a graded candidate:
  $24.58 in early August, $12.34 the following week, **$10.54** last week. The share priced under
  $10 went 23% → 37% → **41%**; median 20-day volume fell 796k shares → 425k. The $500M market-cap
  floor and the $1M average-dollar-volume floor therefore bite more often on the same rule. Neither
  threshold has been touched — `backtester/filters.py` has no commit in the window.
- **The extension gate took 2.2 names a day, up from 0.8**, and every one of them earns it: WETO
  up 581% in five days, CURX up 2,696%, ELAB up 989%, IPST up 413%, BANL up 169%, XHLD up 191%.
  Only two of the eleven (FIEE at 51%, SCTX at 61%) sat near the 50% line that was in force at the
  time. A thin tape leaves runaway micro-caps as a bigger share of what is left; the gate is doing
  exactly the job it was built for.
- The catalyst grader is **not** tightening. Share of graded names coming back stronger than
  routine, per period: 17.6% in July (07-06 → 07-24), 13.9% (07-27 → 07-31), 24.0% in the burst
  week (08-03 → 08-07), 31.6% (08-10 → 08-14), **25.0% last week (08-17 → 08-21)**. Last week runs
  *above* July and above late July. If anything the grade mix improved.

## Result 5 — no rule tightened admission; the two signed changes both loosened it

Everything checked and cleared:

- **Regime bar.** The HIGH bar is regime-dependent (65 in Bull, 70 Choppy, 75 Correcting, 80
  Crisis). It was **65 — the loosest setting — every day from 08-04 through 08-19**, spanning both
  step-downs, and only rose to 70 on 08-20 when alerts were already at 1-2. The bar never tightened
  during either step.
- **Toggles.** No admission toggle moved in the window. The only `mi_safeguard_state` transitions
  are exit-side: `breakeven_at_broker` (08-10), `profit_take_resting_limit` (08-10),
  `profit_take_oco` (08-17). The real-time gap toggles have been on since 08-01/08-02, before the
  whole comparison period.
- **Filter thresholds.** $500M market cap and $1M average dollar volume: unchanged, no commit.
- **Errors.** No systemic grading failure, rate-limit storm or scan error. The only clusters are
  16 catalyst-extraction failures on 08-07 (fixed that day) and 11 truncation events on 08-10 —
  neither large enough to move a daily alert count, and both on the wrong side of the steps.
- **The two signed changes in the window both ADD candidates.** The gap floor moved 10% → 9% on
  08-19 (acting from 08-20) and the extension cap 50% → 75% on 08-22.

**One gate is quietly costing more than it was measured to cost — but it caused neither step.**
The real-time sustain rule (a live ≥10% gap that fails to hold three consecutive bars is not
admitted) declined **10.2 names/day** in the burst week, 4.4 the following week, and 5.4 last
week. It is roughly flat in absolute terms while the board halved, so its share of what would
otherwise arrive grew from about **one in seven to about one in three**. It was sized and signed
on 08-02 against a board three times today's size, it has not changed since, and it therefore
cannot explain a step on 08-10 or 08-17 — but nobody has re-measured what it costs on a thin
board. Stated as a finding, **not as a recommendation**: the rule is signed and live, and any
change to it is the operator's call.

**The 9% gap floor is working and is measurable.** Candidates admitted only because of it: 6 of 19
on 08-20, 7 of 18 on 08-21, 5 of 9 on 08-24. One of them became **the only HIGH alert of 08-21**.
Alert volume still fell because the loosening added roughly six marginal names a day to a board
that had lost twenty-eight — a real gain, swamped by a much larger loss of supply.

## Result 6 — what this means for the two-silent-days revert trigger

The trigger is arm (c) of the catalyst-lattice flip monitor
(`health_checks.run_catalyst_lattice_monitor`, run nightly at 17:30 ET): two consecutive trading
days with zero EP alerts → Telegram naming the trigger, with the revert SQL for the
`catalyst_tier_lattice` toggle. Today was zero. If tomorrow is zero it fires.

**It would be a false signal.**

- Its sibling arm already fired tonight — audit row `catalyst_lattice_monitor_alert`, 2026-08-24
  17:30, kind `high_volume_drop`, last five trading days averaging 1.4 HIGH alerts against 4.19
  over the prior 21. The number is correct; the attribution is not.
- **The lattice has acted for exactly one trading day.** `mi_catalyst_tier_shadow` holds
  `live_side='lattice'` rows for 2026-08-24 only — three tickers. Thirteen of the fourteen days
  the trigger is measuring predate the flag it would revert. Reverting it cannot restore alerts
  that fell before it existed.
- **The threshold is met by ordinary July variation.** Of 22 July trading days, 6 produced zero
  HIGH alerts, and two of those pairs were consecutive: **07-01 and 07-02, and 07-16 and 07-17**.
  The trigger would have fired twice in July on a healthy system with no lattice, no rescale and no
  rebuild.
- **It is one loosening away from having fired already.** 08-21's single alert exists only because
  of the 9% gap floor. Without that signed change, 08-21 and 08-24 would both have been zero and
  the trigger would have fired tonight.
- A zero-alert day on 08-24 is what the arithmetic predicts, not a defect: **9 real candidates
  arrived**, and applying last week's alerts-per-candidate rate (10.3%, from 08-17 → 08-21) gives
  an expected **0.9 alerts**. Zero is an ordinary draw off that. ⚠ That rate is applied to an
  arrival count which is itself the window's outlier (see limitation 2), so treat it as an
  order-of-magnitude check, not a forecast.

The trigger measures alert volume, and alert volume is dominated by how many stocks gap on a given
morning. It therefore cannot separate a quiet tape from a broken gate. That is a statement of what
it can and cannot see — **not a proposal to retune it. Any change to it is the operator's call.**

## What this does NOT answer

1. **The real-time admission layer is upstream of the scan log and was not separated.** #489/#490
   decide which names reach `mi_ep_scan_log` at all, so every add and removal they make shows up
   only as a change in "candidates the scan saw" — this study cannot split that number into "the
   tape offered fewer" versus "the real-time layer admitted fewer". The one piece of it that is
   countable is the sustain rule, reported in Result 5; the flip-up and flip-down arms are logged
   per tick inside the 9:15-9:35 window, so their daily counts are not name counts and were not
   used.
2. **2026-08-24 is one day and it is an outlier.** Candidates arriving as a share of the day's
   gapping stocks: 71% in July, 95% in the burst week, 74%, 72% — and **47% on 08-24** (9 of 19),
   the lowest ratio in the window. It is also the first trading day after the 08-22 batch
   (pre-score shortlist ordering, the score rescale, the lattice flip, the new universe-floor
   logging). One day cannot distinguish noise from a side effect of that batch. It does not touch
   the conclusion — both step-downs are entirely before 08-22 — but it is an open observation, not
   a quiet tape, and it needs a second and third day before anyone reads it.
3. **Candidates dropped by the delayed universe screen before 08-22 are invisible.** The two D-1
   universe floors only started logging a reason on 08-22 (#570). On 08-24 they accounted for 213
   of the 222 scan-log rows, all sub-$5 or illiquid names (median prior close $1.78), which is why
   the raw 08-24 row count must never be compared to earlier days. Before 08-22 that whole class
   left no trace, so this study cannot say whether it changed.
4. **It says nothing about whether the alerts we did fire were good ones.** This is a count study.
   Whether last week's eight HIGH alerts were better or worse names than the burst week's
   thirty-eight is a separate question, and the 08-22 changes were made precisely to move that
   quality — which this measurement cannot see.
5. **It cannot prove a negative about the 08-22 batch.** It establishes that the batch is not
   responsible for a collapse that began on 08-10 and finished on 08-17. It does not establish
   that the batch is harmless going forward.
