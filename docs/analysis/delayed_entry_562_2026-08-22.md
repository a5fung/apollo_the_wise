# #562 — Pricing the delayed-entry triggers on the stopped-out cohort (2026-08-22)

**MEASUREMENT ONLY. No entry rule, stop, trigger or timing change is made or proposed as
done. Entry timing is entry discipline = the operator's sole authority (THE LINE). $0 —
prod read-only, no LLM calls, no paid data.**

## The question

The conversion rehearsal (`conversion_rehearsal_2026-08-18.md`, plan §0g) established the
mechanism this card tests: our surfaced tail winners are real, but their run starts 7–21
sessions AFTER the EP day, and in 3 of 5 measurable cases the launching base formed days
later and BELOW the EP-day low — so the ORB-day entry is structurally the wrong moment.
The operator's own entry architecture for this window is written in
`docs/setups/delayed_ep_reentry.md` §2026-08-16: a **PIVOT LADDER** (EP-day LOW · EP-day
CLOSE · EP-day HIGH · prior-day high · MA10), each pivot with its own entry and stop, plus
**PROXIMITY-NOT-TOUCH** — switch to the intraday **620 chart** when price NEARS a pivot and
take the turn without requiring a touch (P2: a rigid touch test is the wrong instrument).
The #562 minute backfill (532,057 bars / 893 following-session ticker-days) made this
testable for the first time. This study prices **every trigger the spec names**, at minute
resolution, on the population §0g identified: names we surfaced, ENTERED, and were STOPPED
OUT of. The 08-18 daily-bar sweep (`pivot_ladder_delayed_entry_562_2026-08-18.md`) measured
the DECLINED population with a daily proxy; this is the corrected population and the real
instrument.

## Pre-registration

All definitions below were frozen 2026-08-21 **before any outcome was computed** (probe
header, `562b_probe.py`). Facts already known when frozen, stated for honesty: the §0g
winner shapes (INTC/SMCI/NRIX peaks 7–21 sessions out), the 08-18 daily-ladder results on
declined names, the TEAM 620 worked example, and the #572 engine calibration
(+0.41R/trade sim optimism). 620-turn constants were fixed a priori from the TEAM worked
example (`docs/methodology/620_chart.md`) and were **not swept**. Every arm is reported;
no arm is promoted because it performed.

## Data and provenance

- **Population:** the 44 magna53 stop-out episodes (paper+live, `mi_live_trades`,
  `status IN (closed, stopped)` and last exit reason `stop_hit`) — byte-identical to the
  population `scripts/backfill_forward_minute_bars_562.py` backfilled. Alert dates
  2026-04-17 → 2026-08-19. Includes post-partial breakeven "stops" (e.g. KURA +$21) — the
  population is *exited via stop*, not *lost money*.
- The three lived tail winners from §0g are all in the cohort: **INTC 04-24, SMCI 05-06,
  NRIX 06-08** (HLIT/VPG were infra skips, never trades — not in this population).
- **Bars:** 346,601 one-minute bars for the cohort tickers over sessions +1..+25 after each
  alert (captured once to `562b_minute.psv`); daily OHLC from `mi_daily_closes` through
  2026-08-21 (`562b_daily.psv`); trades + exit timestamps (`562b_cohort.psv`). All 44
  episodes evaluable; median 24 eligible sessions (min 2 — MRVL 08-19, truncated at the
  data edge).
- ⚠ **Return basis (the trap this card was warned about): every return here is measured
  from a MODELED FILL at each trigger's own entry, against that trigger's own stop.**
  `mi_ep_missed_outcomes` and its gap-day-OPEN basis (`missed_outcomes.py:480`) are NOT
  used anywhere in this study. `max_high_*`-style excursions appear only in the MFE
  columns, always labeled as ceilings, never as the verdict.
- **Eligibility:** triggers may only fire at/after the episode's flat timestamp (last exit,
  UTC→ET — verified per episode; e.g. SMCI 07-22 was not flat until 07-27 10:37 ET, so its
  07-23/24 signals are correctly ineligible). Window = following sessions 1..25.

## The triggers (from his spec) and the fill/exit model

One entry per episode per arm; first FILLABLE signal decides; arms evaluated independently
("any one of them can trigger and work"). Signals on 5-min bars resampled from 1-min;
entry = the NEXT 1-min bar's open; signals after 15:54 ET lapse.

| arm | signal | stop |
|---|---|---|
| **EPL-UR** | undercut of EP-day LOW, then 5-min close back above within 2 sessions (same-bar hammer counts) | min low since undercut |
| **EPC-REC** | 5-min close below EP-day CLOSE arms it; first 5-min close back above | min low of the below-stretch |
| **620@EPL / @EPC / @PDH / @MA10** | first qualified **620 turn** with the cross bar inside pivot ± 0.5×ADR$ — proximity, touch NOT required | **low-of-day-so-far** (the operator's TEAM stop basis) |
| **620-ANY** | first qualified 620 turn anywhere (the #545 question: the timing tool alone on an already-qualified name) | low-of-day-so-far |
| **EPH-BRK** | first 1-min high ≥ EP-day HIGH (resting buy-stop) | prior session's low |

**The 620 turn (one definition, all arms):** MACD(6,20) on 5-min closes with an EMA-9
signal line, continuous across sessions; qualified bullish cross = MACD crosses above
signal with MACD < 0, the fast line's hour-scale low made just before the cross (the
hook), and a basing range ≤ 0.4×ADR$ over the prior 40 minutes — the three computable
conditions of the TEAM worked example.

**Exits:** `geometry_sweep_572.simulate` reused unchanged — +2R partial (half) →
breakeven → MAX(SMA10,SMA20) daily-close trail → 20-trading-day time stop; entry day
managed at 1-minute resolution, conservative ordering, gap-through stops fill at the open.
Hand-verified end-to-end on SMCI 07-22 (+5.45R chain reproduces from raw bars) and NET
08-07 (signal, entry, stop all reproduce with independent code).

**Units:** realized R (per-trade risk) AND ADR units (pnl / entry×ADR%) — R alone is
volatility in disguise on sub-1% stops. **Baseline: 0R** (we are already stopped out;
doing nothing costs nothing). **Bar to clear: +0.41R/trade** — this exact engine's
measured optimism against live fills (#572 calibration).

## Result 1 — the ladder, all eight arms (conservative sequencing)

| arm | fires /44 | win% | med R | per-trade R | sum R | per-trade ADR | ≥+2R | full stops | med stop width |
|---|---|---|---|---|---|---|---|---|---|
| EPL-UR | 34 | 24 | −1.00 | −0.56 | −18.97 | −0.31 | 0 | 26 | 2.2% |
| EPC-REC | 36 | 31 | −0.66 | −0.06 | −2.29 | +0.01 | 2 | 16 | 5.3% |
| 620@EPL | 34 | 21 | −1.00 | −0.44 | −15.06 | −0.05 | 2 | 26 | 1.7% |
| **620@EPC** | 31 | **39** | −1.00 | **+0.21** | **+6.48** | +0.19 | 4 | 17 | 2.1% |
| 620@PDH | 23 | 30 | −1.00 | −0.34 | −7.91 | −0.12 | 0 | 14 | 1.5% |
| 620@MA10 | 40 | 35 | −1.00 | −0.40 | −15.95 | −0.06 | 2 | 24 | 1.7% |
| 620-ANY | 44 | 45 | −0.81 | +0.04 | +1.76 | −0.00 | 4 | 22 | 1.6% |
| EPH-BRK | 28 | 29 | −0.92 | −0.03 | −0.75 | +0.07 | 2 | 14 | 7.7% |

Optimistic sequencing moves nothing materially (entry days are minute-resolved; the
cons↔opt spread is ≤2R everywhere). The single labeled sensitivity — stop distance
DOUBLED, the era-C 2×-risk shape, signals unchanged — flips **no** arm positive either:
620@EPC falls to +0.05R/trade, EPL-UR gets WORSE in ADR terms (−0.39/trade; the undercut
names keep falling and the wider stop just loses more per hit).

## Result 2 — the best cell does not clear the bar, and its sum is two open marks

**620@EPC** (a 620 turn within 0.5×ADR of the EP-day close) is the best-performing named
trigger: 31 entries, 39% win rate, +0.21R/trade. It does not survive scrutiny:

- **+0.21R/trade is HALF the engine's own measured optimism (+0.41R/trade).** On
  calibration alone this rounds to zero.
- **Ex-top-2 the cell is −3.74R.** And the top 2 — SMCI 07-22 (+5.45R) and TEAM 08-07
  (+4.77R) — are both **`data_end` marks on positions still open at the 08-21 edge**, not
  banked results.
- Median trade: −1.00R. 17 of 31 are full stops.

## Result 3 — the decisive split: every arm's CLOSED trades are net negative

| arm | closed n | banked R | open n | open-mark R |
|---|---|---|---|---|
| EPL-UR | 34 | −18.97 | 0 | — |
| EPC-REC | 33 | −7.38 | 3 | +5.08 |
| 620@EPL | 34 | −15.06 | 0 | — |
| 620@EPC | 29 | **−3.74** | 2 | +10.22 |
| 620@PDH | 22 | −8.17 | 1 | +0.26 |
| 620@MA10 | 40 | −15.95 | 0 | — |
| 620-ANY | 42 | −4.19 | 2 | +5.95 |
| EPH-BRK | 23 | −7.86 | 5 | +7.11 |

**Eight arms, zero banked-positive.** Every positive reading in this study sits in
still-open August positions (SMCI, TEAM, and friends) that the 20-day windows have not
settled. Under P8 those marks are provisional by definition; the settled evidence is
uniformly negative.

## Result 4 — the mechanism: the triggers FIND the runs; the stops die first

Among full-stopped entries, the favourable excursion over the following 20 sessions
(almost entirely post-stop — a full stop means the +2R partial never filled first):

| arm | full stops | med MFE (ADR units) | reached ≥2×ADR after entry | reached ≥4R |
|---|---|---|---|---|
| EPL-UR | 26 | 0.91 | 10 | 12 |
| 620@EPL | 26 | 1.34 | 11 | 16 |
| 620@EPC | 17 | 1.74 | 8 | 11 |
| 620@PDH | 14 | 1.62 | 6 | 8 |
| 620@MA10 | 24 | 2.11 | 12 | 14 |
| 620-ANY | 22 | 1.30 | 10 | 15 |

(The R column is inflated by tiny stops and is shown only because R is the house unit;
the ADR column is the honest one.) Roughly **half of the 620-arm entries that stopped out
were sitting in front of a ≥2×ADR move** — the trigger located the turn; the stop died to
noise before the move. Median stop widths on the 620 arms are 1.5–2.2% (NET's was
0.27%) under names whose ADR is 4–8%. **This is the same disease §0g measured at the
ORB entry — "the EP day is violent, the run starts later, no stop width survives it" —
now reproduced at the delayed entry.** And the 2×-stop sensitivity shows widening alone
does not fix it: the loss per hit doubles and the harvest still surrenders the later run.

## Result 5 — the three known tail winners: re-entered, and still mostly lost

Recall read only — the cohort was NOT selected by outcome, and nothing here is evidence
(n=3); it is the existence proof the arms were built for, checked by name:

- **INTC 04-24** (later +10.9×ADR): 620-ANY and 620@EPC re-entered d+1 → **−1R each**
  (48R of excursion followed the stop). **EPC-REC d+2 (04-28, entry 82.91, stop 80.80)
  → +7.13R banked** on the SMA trail — independently consistent with the operator's own
  observation that the INTC EP-close pivot filled 04-28 and paid (+9.18R under his
  harvest). EPH-BRK → +3.10R.
- **SMCI 05-06** (+9.5×ADR): six arms fired; the tight-stop arms all −1R; EPC-REC +1.67R,
  EPH-BRK +2.41R.
- **NRIX 06-08** (+11.9×ADR): six arms fired; five stopped −1R (620@EPC's stop was 0.62%
  wide; 101R of excursion followed); EPH-BRK +1.80R.

The pattern inside the winners matches Result 4: the arms that kept anything are the
**wider, structure-stopped** ones (EPC-REC 2.5–5% stops, EPH-BRK ~7%), not the tight 620
arms — but across the whole cohort those same wide arms bleed the winners' gains back on
the losers (Result 1). The trigger can locate; it cannot rank.

## Result 6 — the lived cases: TEAM and NET

- **TEAM 08-07** — the operator's own worked case. 620@EPC catches it d+1 (08-10 11:40
  cross, entry 148.14) and marks **+4.77R, still open** — the one arm that catches TEAM is
  the mechanism he actually uses. But note what the mechanical version misses: **his real
  TEAM entry was a DAY-0 re-entry** (stopped 09:43, back in at 12:05 at 144.39 off the 620
  turn). This study's window — following sessions only, matching the backfill — cannot
  see day-0 re-entries at all. His entry is in an arm this study did not price.
- **NET 08-07** — the proximity+620 instrument did exactly what it was designed to do:
  located the 08-17 10:30 turn near the EP-day close without requiring a touch. The
  mechanical low-of-day-so-far stop was **0.27% wide** and died the same day (−1R), with
  4.3R of excursion after. A stop that narrow under a 5.3%-ADR name is noise, not risk
  management — the rigid rendering of a discretionary tool, which is P2's exact warning.

## Result 7 — instrument notes

- **620-turn multiplicity: 1.12 qualified turns per session** across the cohort's 885
  eligible sessions — the turn definition alone is NOT selective; all selectivity comes
  from the pivot condition. Any future use of "a 620 turn fired" as a standalone flag
  would fire daily on almost every name.
- Proximity worked as specified: entries did not require touches, and the NET/INTC class
  (turn near but above the pivot) was captured by construction.

## ⚠ What this study does NOT answer

- **The day-0 re-entry arm — the operator's actual TEAM move — is unpriced.** The window
  was pre-registered as following sessions 1..25 (matching the backfill); day-0 bars exist
  for alert days (`persist_alert_day_paths`), so this is testable next at $0. Given TEAM,
  it is the most conspicuous untested shape (P7: the remaining probability mass).
- **The August cluster is unsettled.** Two-thirds of the study's entire positive R is two
  open marks (SMCI, TEAM). Re-running when those windows close (~mid-September) is $0 and
  pre-registered here: the verdict below could soften or harden.
- **44 episodes, one regime, 3 known tail winners.** Tail statistics on n=23–44 per arm
  are thin by construction (P3 tension, stated: a tail read wants more N than this cohort
  has). Every conclusion is conditional on the current selector's population (P8).
- **No portfolio/slot effects** (P4): arms were priced independently; a live book would
  face slot competition and ordering.
- **Sim, not fills**: entries and exits are reconstructions on real bars; the engine's
  measured optimism (+0.41R/trade) is cited against every positive, but slippage and
  borrow are not modeled.
- **The harvest is one policy** (+2R partial → breakeven → SMA trail). Result 4 says the
  binding constraint is stop/harvest geometry, not trigger location — but this study did
  NOT search harvest space (that would be sweeping into entry-discipline design, which is
  the operator's).

## Verdict, plain words

**None of the eight delayed-entry triggers clears the bar.** The best — a 620 turn near
the EP-day close — converts at +0.21R per trade on paper, which is inside this simulator's
own measured optimism; its entire positive sum is two still-open August marks; and every
arm's CLOSED trades net negative (eight for eight). The clean negative is real, but it is
**not** "delayed entry is dead" — it is: **the delayed-entry triggers locate real turns
(half their stop-outs sat in front of ≥2×ADR runs, and they re-entered all three known
tail winners) and the day-0 stop geometry at the re-entry kills the trade before the run,
exactly as it does at the ORB entry.** The leak this cohort keeps measuring is not WHERE
we enter. It is that a 1–2% stop under a 5–8%-ADR name dies to noise wherever it is
placed, and the one lived counter-example (the operator's TEAM re-entry) survived on
discretion the mechanical version does not have.

**What would settle it** (all $0, in order of information per dollar):
1. **Price the day-0 re-entry arm** on the alert-day bars — the operator's own TEAM shape,
   the one arm this study could not see.
2. **Re-run this probe when the August windows settle** (~mid-Sept) — the open marks are
   the only thing standing between "weak negative" and "clean negative".
3. The stop/harvest geometry question Result 4 isolates is **entry discipline = the
   operator's fork**, and the evidence handed to it is: trigger location is not the
   binding constraint; stop width relative to ADR is.

## Files

- This doc: `docs/analysis/delayed_entry_562_2026-08-22.md`
- Probe (pre-registration in header + all arms): scratchpad `562b_probe.py`; sensitivity
  `562b_sens.py`; verification `562b_verify.py`, `562b_post.py`
- Captures (pulled once, read many): scratchpad `562b_cohort.psv`, `562b_daily.psv`,
  `562b_minute.psv` (346,601 bars); outputs `562b_out.txt`, `562b_detail.csv`
- Prior related: `conversion_rehearsal_2026-08-18.md` (the population + mechanism),
  `pivot_ladder_delayed_entry_562_2026-08-18.md` (daily proxy, declined names),
  `geometry_sweep_572_2026-08-18.md` (the exit engine + its calibration),
  `docs/methodology/620_chart.md` (the 620 spec + TEAM worked example)
