# #557 — What the two cooldowns actually cost (2026-08-21)

**MEASUREMENT ONLY. No safeguard, cooldown, threshold or strategy changed. Any change is
CHANGE_PROCESS + operator sign-off (THE LINE).**

## The question

The 2026-08-09 weekly digest put 4 of the 8 biggest missed moves on two different cooldowns:
the **60-day same-ticker cooldown** (ALOY "+47% peak", IREN "+30%") and the **circuit-breaker
cooldown** (APPS "+28%", FET "+26%"). Those are peak excursions, not fills. This study models
what a real ORB entry and our real exit rules would have produced, and nets each mechanism
against what it prevented. The two mechanisms are kept separate throughout — they block
different populations at different points in the pipeline.

## Where each gate sits (this controls what the numbers mean)

- **60-day cooldown** — `ep_detector.py:2953-3008`, mid-cascade. A blocked name has passed
  only the gap floor, top-20 cap and RVOL gates. It was NEVER tested against extension,
  ADV/ATR/market-cap, M&A, catalyst grading, score ≥ 50, or the HIGH bar — `ep_score` is NULL
  on every one of the 114 blocked rows. The headline count is not a population of trades.
  Earnings carve-out: gap ≥ 15% + earnings day bypasses the cooldown (≈6 distinct ticker-episodes
  ever, e.g. NBIS 05-13, AVAV 06-30) — so the blocked cohort structurally EXCLUDES the
  strongest re-fire class.
- **Circuit breaker** — `entry_pipeline.py:551-563` → `live_tracker.py` safeguards, at ENTRY
  SUBMISSION. A breaker-blocked name passed everything and scored HIGH; the only gate left
  after it is the fill itself. This cohort IS a population of would-be trades.
  Config: `constants.py:334` — 10 consecutive losses (per account mode), 24h cooldown from the
  LATEST loss close, realized partials count as outcomes since 2026-08-05.
  (Doc nit found on the way: `skip_reasons.py:102` still humanizes this as "5-loss circuit
  breaker tripped" — the threshold has been 10 since the July change.)

## Data and provenance

- `mi_ep_missed_outcomes`: 114 cooldown ticker-days (2026-04-20 → 2026-08-20, 75 distinct
  tickers — the full extent of the table's backfill, 4 months, well past the 60-day minimum)
  and 21 breaker-blocked ticker-days on 6 block days (2026-04-29 → 2026-08-05).
- **Return basis verified**: `missed_outcomes.py:480` — every `ret_*` and `max_high_*` is
  measured from `open_d0`, the gap-day OPEN. That is a day-2 chaser's price, not our ORB-high
  entry, and `max_high_*` is a maximum favourable excursion nobody could time. Neither is a
  fill. They are used below only as the unconditional context, never as the verdict.
- Fill model inputs: `mi_intraday_bars` 1-minute bars (17 of 21 breaker ticker-days have full
  coverage; only 22 of 114 cooldown ticker-days have ANY bars — bars exist only where some
  other lane pulled them, so the cooldown fill subsample is BIASED and labelled as such) +
  `mi_daily_closes` OHLC for the D1+ continuation.
- `mi_live_trades` + realized-partial exits (for the held-before split, the breaker streak
  reconstruction and the position-cap counterfactual). `mi_audit_log` for block timestamps.
- Captures (pulled once, read many): `scratchpad/557_batch1.out`, `557_batch2.out`,
  `557_batch3.out`; computation `scratchpad/557_analyze.py`. All read-only; $0 spent.

### The fill model (stated once, applies to both cohorts)

Entry = stop-buy at the 09:30-09:31 ORB high, live 09:31, cancelled 10:00 if the price never
crosses (this is the live mechanic). No slippage assumed. Exit = the rules in force on the
blocked dates: stop at ORB low, 1/3 partial at +2R, stop to breakeven after the partial, then
daily-bar continuation (a day that hits both stop and target counts the stop first —
conservative). Marks at 5 and 20 trading days. The operator-signed 2R stop (2026-08-16) is run
as a sensitivity on everything. Fill-bar ambiguity: a stop hit inside the fill minute counts
only if that bar CLOSES through the stop.

---

## Mechanism (a) — the 60-day same-ticker cooldown

### Result 1 — the unconditional distribution: blocked names go DOWN

Open-basis, all 114 ticker-days (no outcome conditioning):

| horizon | n | mean | median | positive |
|---|---|---|---|---|
| 5d close | 109 | −0.7% | **−2.7%** | 42% |
| 20d close | 81 | **−15.0%** | **−20.2%** | 28% |

The tail exists (P3): peak ≥30% within 20d on 26% of names, ≥50% on 11%, ≥100% on 1 name.
The SHAPE is pump-and-fade: big peaks over deeply negative 20-day closes. 34% of names are
−10% or worse at 5 days. (20d closes exist only for alerts through ~07-22 — Apr-Jun heavy.)

### Result 2 — the digest's two names, modeled as trades, are not "+47%" and "+30%"

- **ALOY 07-29** ("+47% peak", later a +98% 20d peak): minute bars exist. Filled 09:41 at
  8.26; the ORB-low stop (7.62) was touched at 15:34 THE SAME DAY — the trade is a **−1R
  loser** under the rules in force. Under the current 2R stop it survives D0 and marks **+1.8R**
  at 20d — a real but ordinary winner, and the position size is halved. The +98% peak was never
  reachable by this system's entry and stop; ALOY also faded to −34% at 20d after its 06-15
  block. When ALOY finally re-fired past the cooldown on 08-10, it scored **24 (routine)** and
  died at the score gate.
- **IREN 07-30** ("+30%"): no minute bars — not modelable, said plainly. Context: IREN's own
  non-cooldown days died elsewhere (07-06 score 45 < 50; 07-20 alerted HIGH but detected 09:51,
  out of window). The cooldown was not the only thing between us and IREN.

### Result 3 — modeled cost of the whole mechanism: one to four losers' worth of risk per 4 months

Chain, each link measured, none assumed:

1. **114 blocked ticker-days** in 4 months.
2. **~20% would have alerted HIGH** — the measured survival rate of names that reach the
  cooldown's position in the cascade (325 HIGHs vs 1,280 downstream kills since 04-20).
  Likely generous for THIS cohort: it excludes fresh-earnings re-fires (bypassed), and its own
  members' non-cooldown days kept dying at the score gate (ALOY 24, IREN 45). → **~23 alerts**.
3. **Modeled per-alert outcome** (22-day covered subsample, 16 fills + 6 no-fills):
  **+0.17R** per alert at 5d under the ORB-low stop (sum +3.8R), **+0.07R** under the current
  2R stop (sum +1.6R); at 20d **+0.09R / +0.03R**.
4. **Total: roughly +1R to +4R per 4 months** (≈ $25-200 at live $25-50-per-R sizing) —
  BEFORE charging the slot cost of ~23 extra alerts competing for 5 positions (P4).

The subsample's big-peak names convert badly: ALOY (+98% peak) → −1R, TE 05-18 (+86% peak) →
−1R, HIMX (+63% peak) → +0.67R. **The three biggest modelable "monster misses" sum to −1.33R.**
Peak-ranked miss lists select exactly the gap-and-fade shape our ORB-high entry buys at the top
of and our stop then catches.

### Result 4 — what the cooldown PREVENTED (the netting)

- **Its designed target — names we previously held — keeps being a graveyard**: 14 blocked
  ticker-days on previously-held names; 5d mean **−12.5%**, 1 winner in 12 (extends the
  07-26 study's 0-for-11 at n now 12+14 combined; same direction, no reversal).
- The never-held collateral (100 ticker-days): 5d median −1.3%, 20d median −20.2% — a coin
  flip at 5 days that rots by 20.
- **The one identifiable loosening signal is unchanged and still pre-registered**: blocked
  names with gap ≥ 15% ran +4.4% mean / +2.8% median at 5d (n=27, both measures positive)
  vs −2.4% / −5.2% for gap < 15% (n=82). That is `cooldown_admission_unassumed`'s territory;
  its bar is n≥30 with no pre-committed criterion. This study adds 2026-07-21→08-20 data and
  the split held.

### Verdict (a), plain words

**The 60-day cooldown is cheap.** Its realistic 4-month cost is one to four live losers' worth
of risk — not the two headline moonshots, both of which either lose under our own rules (ALOY)
or died at other gates on their other attempts (IREN, ALOY again). Against that it keeps
blocking re-entries into previously-held names that go on to lose 12% in a week, and it keeps
~23 alerts per 4 months out of a 5-slot book. On this evidence the digest's framing was
selection bias on peaks, same as the 07-26 finding. The only loosening with data behind it is
the gap ≥ 15% re-fire class, which is already registered for an unassumed analysis at n≥30 —
that ruling is the operator's, not this card's.

---

## Mechanism (b) — the circuit-breaker cooldown

### Result 5 — two eras that must not be averaged

- **Era A (Apr-May, threshold was 3 losses, paper)**: 9 blocks. Modeled: NXPI **+6.5R** and
  INOD **+3.4R** missed at 20d (the known 05-08 INOD case), 2 no-fills, 1 degenerate (KALV's
  2-cent ORB range — nominal +0.67R, meaningless dollars), 4 not modelable (no bars: BE, STX,
  BILL, LASR — open-basis 5d: +3%, +18%, −2%, −2%). A 3-loss breaker in a ~20%-win-rate system
  fires constantly and was genuinely expensive. **That configuration no longer exists**; its
  cost must not be billed to the current breaker.
- **Era B (Jul-Aug, current 10-loss config, live)**: 12 blocks on 4 days, all inside one real
  14-loss streak. This is the era that measures today's safeguard.

### Result 6 — the current breaker's blocks were, in aggregate, trades worth missing

Era B, modeled under the rules in force (17 of 21 have minute bars; era B has 11 of 12, KODK's
ORB range is zero — not modelable):

| name | date | modeled outcome |
|---|---|---|
| CORZ 07-28 | no fill — order would have cancelled at 10:00 | 0 |
| TER 07-29 | filled, stopped D0 09:41 | **−1R** |
| COHU, FLNC 07-31 | no fill | 0 |
| FET 07-31 | filled, +2R partial, then breakeven-stopped same morning | **+0.67R** |
| MPWR, NWL 07-31 | filled, stopped D0 | **−1R each** |
| APPS 08-05 | filled 09:32 at 13.15, stopped D1 at 11.90 | **−1R** |
| KMT 08-05 | no fill | 0 |
| KTOS, TATT 08-05 | filled, stopped D0 / D0+1min | **−1R each** |

**Net: −5.33R avoided** (−4.33R cap-aware: with PLTR held on 08-05 the 5-position cap would
have blocked TATT, the last in the submission order, anyway). Under the current 2R stop the
answer is the same: **−4.96R at 5d, −5.64R at 20d**. The verdict does not depend on the stop
rule. At live sizing that is roughly **$110-190 the breaker saved** in two weeks.

**The digest's two names net −0.33R combined**: APPS ("+28% peak") entered at 13.15 — 10%
above the open the digest measures from — and stopped out the next day for −1R under either
stop rule; FET banked +0.67R and was breakeven-stopped 3 minutes later (its ORB was 0.6% wide —
the peak was +42% but the rules in force never let the position see it).

### Result 7 — the self-perpetuation pathology is REAL and confirmed, but on this sample it saved money

Every era-B window was armed by a SINGLE small loss closing intraday, 24h from that close:

| block day | armed by | loss | window expiry (ET) | blocks fired | breaker life left at block |
|---|---|---|---|---|---|
| 07-28 | SMCI closed 07-27 10:37 | −$15 | 10:37 | 09:31 | 67 min |
| 07-29 | QBTS closed 07-28 09:36 | −$22 | **09:36** | 09:31 | **5.4 min** |
| 07-31 | FTNT closed 07-30 09:37 | −$7 | **09:37** | 09:31-09:35 | **2-7 min** |
| 08-05 | BLZE closed 08-04 15:50 | −$37 | 15:50 | 09:31 | full day |

The CLAUDE.md description checks out exactly: 2026-07-31 was 6 alerts / 0 entries (5 breaker +
BLZE detected 09:56, out of window). The cadence it produces is block-day/trade-day
alternation: the >24h escape valve lets one trade through (FTNT 07-30), that trade loses, and
its own close re-arms the next morning's block. **Six of the 12 era-B blocks fired while the
breaker had ≤7 minutes to live, with the ORB submission window open until 09:45 and no retry
in the pipeline** — a $7 FTNT loss silently cancelled five HIGH entries the next morning.

The honest twist: those near-expiry blocks (TER; the 07-31 five) modeled to **−1.33R net** —
the pathology cost nothing THIS time. It is a real single-point-of-failure mechanism whose
downside simply has not been drawn yet; what ended the whole streak was the operator-signed
partials rule (2026-08-05): PLTR's +$33 partial at 09:45 that same morning broke the streak,
and no breaker block has occurred since.

### Verdict (b), plain words

**In its current 10-loss configuration the breaker has EARNED its keep**: the 12 entries it
blocked in Jul-Aug net to about **−4 to −5R avoided** (~$110-190 at live sizing), robust to
the stop rule, and its two headline "misses" (APPS, FET) combine to −0.33R once actually
modeled. The expensive breaker in the record was the extinct 3-loss version. The
self-perpetuating 24h re-arm is real, confirmed, and twice came within 7 minutes of being pure
deadweight — but on the only sample we have it blocked losers. If the operator wants the
pathology priced for a fix (e.g. re-check at expiry inside the ORB window), that is a
safeguard change: CHANGE_PROCESS + sign-off. Nothing here recommends weakening the breaker on
this evidence.

---

## What this study does NOT answer

- **A 5-slot / order-priority replay was not run** (P4). The ~23 cooldown re-fire alerts per 4
  months would displace OTHER candidates from the book; the marginal displaced trade's value is
  not measured here. The +1-to-+4R "cost" is therefore an UPPER bound on the benefit of
  loosening.
- **92 of 114 cooldown ticker-days have no minute bars — no fill model is possible for them**,
  including four of the five biggest uncovered peaks (HQ +137%, VCX +96%, FCEL +88%, IREN
  +51%). The per-alert R used in Result 3 comes from the 22 covered days, which are covered
  precisely because some other lane cared about them — a bias with unknown sign. It cannot be
  ruled out that one uncovered name was a genuine tail winner under our rules; ALOY (covered,
  −1R off a +98% peak) is the reason not to assume it.
- **The 20d marks for the 08-05 era-B names are truncated** (~11 trading days of data at
  capture). APPS was already stopped; only KODK is fully unmodeled in era B.
- **Slippage is zero in the model.** Real stop-buy fills on fast crosses (APPS, FET) would be
  slightly worse; direction known, size unmeasured, small at $250-1,000 positions.
- **Era B is one losing streak in one regime.** n=12 blocks, 4 days, all inside the same cold
  stretch. A breaker window that lands on a real winner cluster would look different; this
  study measures what happened, not every future.

## Files

- Analysis (this doc): `docs/analysis/cooldown_cost_557_2026-08-21.md`
- Computation + captures: session scratchpad `557_analyze.py`, `557_batch{1,2,3}.out` (not
  committed; re-derivable from the queries embedded in `557_batch{1,2,3}.sql`)
- Prior related studies: `docs/analysis/cooldown_60d_effectiveness_2026-07-26.md` (held-before
  split, #170 shadow, the gap≥15 discriminator — all confirmed on the extended window),
  `docs/analysis/adv_floor_556_2026-08-20.md` (the method template).
