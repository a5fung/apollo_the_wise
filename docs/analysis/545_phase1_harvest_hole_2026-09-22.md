# #545 Phase 1 — THE DAY-1 HARVEST HOLE (2026-09-22)

**Status: EVIDENCE ONLY.** No strategy, stop, target, partial, trigger, sizing or safeguard is
changed. No live table is written. This card produces the grid and the measured tail; it does
not choose a stop, target or partial — that is the operator's, under CHANGE_PROCESS.

---

## Read this before any analysis. Every card gets it verbatim (`ANALYSIS_CARD_PREAMBLE.md`)

**THE GOAL:** *Make EPs profitable: filter the universe on all the factors that matter, not just
a gap, so a small win rate is carried by winners large enough to give positive expectancy.* At a
~20% win rate with 1R losers, the average winner must exceed 4R just to break even. Win rate and
reward are ONE target, never two.

**Rank order:** RECALL (does it catch real EPs at all) → EXPECTED RETURN (mean and median, n on
every figure) → CAPTURE (of the move that was available) → THE TAIL (P3 — how many reach 4R+).

**Win rate is a SELECTION measure, not an entry/exit measure** — it cannot be moved by a stop,
target or harvest rule, so it is reported here as a descriptive column only, never used to rank
a cell. Ranking is on the tail first, per `docs/methodology/analysis_standard.md` §THE STATISTIC
(operator, 2026-09-05: *"big tail is the key ingredient, median can be somewhat managed with
entry and exit"*).

⚖ THE LINE: strategy, entry/exit discipline, sizing, targets and safeguards are the operator's
sole authority. This card is evidence; it never flips anything.

---

## The decision this serves

The operator ruled 2026-09-22: *"we need to find the right entries and exits for any new setups,
those are undetermined."* For the EP setup specifically, the design doc
(`docs/design/545_entry_exit_program_2026-09-05.md` §0) already found that **the day-1 entry
finds the tail; the stop and the harvest give it back** — the single rule identified as giving
back the most is the breakeven-at-partial step. Phase 3 (the prior card) never ran the harvest
shapes that REMOVE a rung entirely, or ADD a second one. This card runs exactly those, at $0, on
data already captured, so the next fork the operator is asked to decide (keep/remove breakeven,
tighten the stop, add a second partial) has a number beside it instead of a hunch.

**What would change the read:** a cell that clears the pre-stated pass bar (below) is a
candidate for the forward gate (#482's live-fill counterfactuals); a cell that does not clear it
is recorded as evidence AGAINST, not silently dropped.

---

## Method and population

**Population = P-REPLAY** (design doc §1, not re-derived here): **267 live-source `mi_ep_alerts`
alert campaigns**, 2026-05-11 → 2026-08-28 (270 rows in the raw capture; 3 same-millisecond
duplicate inserts — MANE 07-15, KMT 08-05, ACMR 08-07 — collapsed to one campaign per
ticker/day, the live system's own constraint). Every campaign is re-admitted under TODAY's
scorer (`RULESETS["era_c"]`'s admission stack: score-separation weights, bar 70/regime-adjusted)
and re-walked from stored minute/daily bars through the harness's LIVE code paths
(`validate_orb_entry`, `stop_limit_buy_price`, `profit_target_r_per_share`, `seed_exit_state` /
`apply_daily_exit_step`) — never a re-implementation. Horizon: `LAST_SETTLED = 2026-08-31`; a
campaign still open at the horizon carries a MARK, never a return. Source captures:
`scripts/ep_replay_data/_pull2_out.txt`, `_pull3_out.txt`, `_pull4_min.tsv.gz`,
`_pull5_out.txt` (unchanged, 09-01 capture).

**Admission funnel** (unchanged from the design doc, restated because every number below is cut
by it): 267 campaigns → **admit 145** (re-scored) / reject 81 / abstain 41 (float-band
straddle) → of the admitted, **65 settle under the live stop** (46 ex-May), 2 remain open, the
rest abstain (1-minute-grain ordering) or never cross the ORB high.

**"The live ladder" baseline, stated explicitly because the deployed stack has since moved:**
this card uses `RULESETS["era_c"]` (entry−2R stop, +2R partial at 1/3, breakeven arms the
moment the partial fills, SMA10/20 trail) as "LIVE" — the same convention the design doc uses
throughout (its §3.1–3.2 "LIVE" tag) and the baseline every reused cell in this card's brief
(`era_c_partial_none`, `era_c_no_breakeven`, `era_c_partial_5r/8r/10r`, `era_c_pnone_be3`) is
built from. **`scripts/live_rules.py` (re-run today, 2026-09-22 07:30 PDT, prod reachable, 0
drift findings) confirms the ACTUALLY deployed MAGNA53 stack today is `RULESETS["current"]` /
`era_d`** — an 8R partial with price-armed breakeven at +3R, flipped live 2026-09-06, one day
after the design doc's "LIVE" snapshot. That later flip is a SEPARATE, already-decided change
and not part of this Phase 1 grid (see "what this does not answer").

**Harness:** `scripts/ep_replay.py` (this card adds one field, see below) driven by a new probe,
`scripts/probes/_545_phase1_harvest_sweep.py`. Walks all 267 campaigns under 17 cells (1 live
baseline + 16 harvest variants) and writes `scripts/probes/_545_phase1_harvest_sweep.tsv`
(4,539 campaign rows) and `..._out.txt` (this run's full stdout — every number in this document
is read from that file, not re-derived by hand). **`stop_width_pct < 0.5` near-zero-stop rows:
0 excluded from the LIVE cell** (checked, not assumed — same as the design doc's Phase 3 finding
on this population).

**`python scripts/ep_replay.py validate` — run before AND after the code change, byte-identical
output both times** (`✅ VALIDATION PASS`, stop-formula 100%, entry-decision 100%, exit-class
97%, realized-R 83%, all at or above the 2026-09-01 baseline floors). Confirms the new field is
opt-in only and disturbs nothing already validated against real fills.

---

## What changed in the harness (the one-rule addition the card scoped)

`scripts/ep_replay.py`:

1. **`RuleSet.second_partial_r: float | None = None`** — a second partial rung, in the SAME R
   frame the first partial (`intraday_partial_r`) uses. `None` (default) → every existing
   rule-set is byte-identical (confirmed by the validate run above). Fires once, taking HALF of
   whatever remains after the first rung (so a clean 1/3-1/3-1/3 split when both fire).
2. **Scope, stated and enforced by `walk_campaign`, which raises rather than silently ignoring
   the field:** (a) requires `intraday_partial_r` to be set — there is no "second" rung without
   a first; (b) refuses `runner_rule="live"` — arming the second rung against the canonical
   ladder function (`apply_daily_exit_step`) would need re-deriving that function's own state
   tracking outside itself, which breaks the harness's fidelity contract. It is available on
   every `RUNNER_RULES` runner (`hard`, `t3`, `t5`, `sma10`, …).
3. **Scope, stated:** only checked in the FORWARD DAILY WALK (post day-0) — a day-0 intraday
   second-rung fire (both rungs inside the entry day's minute bars) is out of scope for this
   half-session card and would need the same same-bar ordering machinery the first target
   already has. Not silent: see the field's own comment in `scripts/ep_replay.py`.
4. Same-day stop-vs-second-rung ordering is unknowable at daily grain, so it **abstains**
   (`fwd_stop_and_target2_same_day`) — mirroring the existing first-target/resting-stop abstain.

The "no partial, no trail" cell (**stop + hold**) needed **no code change**: `RuleSet` already
exposes `trail_mode="none"` (added 2026-09-06 for the trail sweep), so
`replace(RULESETS["era_c_partial_none"], trail_mode="none")` is a pure stop-and-hold rule-set.

**Tests (2 new, `tests/test_ep_replay.py`):**
- `test_second_partial_rung_books_at_its_own_level_after_the_first` — pins a synthetic campaign
  (first partial at 12.0, second rung at 15.0, final third stopped at the original 8.0 floor)
  to `realized_r == 5/6` exactly. **Mutation proof:** commenting out the
  `take_second_partial(target2, d)` call collapses the result to −1/3 (plain "hard" behaviour) —
  confirmed by actually running the mutated code, not asserted; reverted and re-confirmed green.
- `test_second_partial_validates_its_preconditions_and_abstains_same_day_as_the_stop` — the two
  `ValueError` guards (no first rung; `runner_rule="live"`) and the same-day abstain ordering.
  **Mutation proof:** disabling the abstain condition (`if False and hit_tgt2 …`) turns the
  abstain into a silent `open_at_horizon` — confirmed by running the mutated code; reverted.
- Full suite: `tests/test_ep_replay.py` 44/44 pass (42 pre-existing + 2 new), unchanged.
  `tests/ -k "ep_replay or 545"` 80/80 pass.

---

## The grid — tail first (n on every figure; full detail in `_545_phase1_harvest_sweep_out.txt`)

All cells below share the population (267 campaigns, admitted 145, live-stop-settled 65) and
report: settled ≥3R / ≥5R / p90 → median → sum; the same cut ex-May; settled+marks (censoring);
paired vs the live cell; by regime; the four operator-labelled names (PLTR 08-04, TEAM 08-07,
HTFL 08-14, MRNA 08-19).

### The live ladder (baseline — every other row is measured against this)

| cut | n | ≥3R | ≥5R | p90 | median | sum |
|---|---|---|---|---|---|---|
| settled, admitted | 65 | **0** | 0 | +1.43 | +0.21 | +3.5 |
| settled, admitted ex-May | 51 | **0** | 0 | +1.35 | +0.06 | −2.6 |
| settled+marks, admitted | 67 | 0 | 0 | +1.43 | +0.30 | +5.5 (settled +3.5, marks +1.9 on 2 open) |
| regime Bull (n=40) / non-Bull (n=25) | | 0 / 0 | 0 / 0 | +1.43 / +1.14 | +0.33 / −0.10 | +7.7 / −4.2 |

Operator names: PLTR +1.69R · TEAM +0.33R · HTFL +1.43R · MRNA open mark +1.64R. **None ≥3R** —
matches the design doc exactly (§0: "zero campaigns ≥3R" on this population).

### No partial at all

| cell | settled admitted (n/≥3R/≥5R/p90/med/sum) | ex-May (n/≥3R) | settled+marks (≥3R/sum) | drop-best | paired Δ≥3R | verdict |
|---|---|---|---|---|---|---|
| stop + trail only (`era_c_partial_none`) | 64 / **4** / 1 / +2.49 / −1.00 / +2.1 | 50 / **2** | 4 / +6.4 | 4→3 | +4 (cell 4 vs live 0) | **fails ex-May bar** (2 < 0+3) |
| stop + hold (no trail either) | 50 / **0** / 0 / −1.00 / −1.00 / −50.4 | 36 / 0 | 3 / −18.8 | 3→2 | +0 (15 of 65 dropped, uncomparable) | **fails; triggers the kill-it check** |

`stop + trail only`: the trail alone DOES settle real (non-mark) tail — FTK +7.4R, INFQ +4.0R,
QBTS +3.9R, ARGX +3.3R, all four with an empty MARK tag (realized, not open) — but two of the
four (INFQ, QBTS) are May names, so the ex-May count drops from 4 to 2, one short of the +3 bar.
Operator names: PLTR +2.04R, TEAM +2.55R, HTFL +1.64R, MRNA open mark +1.96R.

`stop + hold`: **every settled cut shows ZERO ≥3R names** (all-alerts, admitted, ex-May all 0).
The 3 names that DO reach ≥3R (TEAM +6.6, ARGX +4.2, PLTR +3.5) are **all three open marks**,
never a settled return — the exact condition the pre-stated "what would kill it" clause names.
Operator names: all four still open at the horizon (PLTR +3.53, TEAM +6.60, HTFL +2.22,
MRNA +1.96 — all marks).

### Partial, no breakeven

| cell | settled admitted (n/≥3R/≥5R/p90/med/sum) | ex-May (n/≥3R) | settled+marks (≥3R/sum) | drop-best | paired Δ≥3R | verdict |
|---|---|---|---|---|---|---|
| trail stays, breakeven never arms (`era_c_no_breakeven`) | 64 / **1** / 1 / +2.00 / −0.33 / +5.3 | 50 / **1** | 1 / +9.0 | 1→0 | +1 | **fails** (needs +3, has +1) |
| `hard` (no trail, rides the original stop) | 52 / **0** / 0 / −0.33 / −0.70 / −33.9 | 38 / 0 | 2 / −9.0 | 2→1 | +0 (13 dropped) | **fails; triggers the kill-it check** |

`hard`: same pattern as `stop + hold` — zero settled ≥3R in every cut; both ≥3R names (TEAM
+4.73, ARGX +3.1) are open marks. Reproduces the design doc's own §3.2 finding for this cell
exactly (paired −20.9R on the 52 common settled rows — matches).

### Second partial rung (5R / 8R / 10R) on top of a tight stop

`hard` after the second rung (no trail, rides the tight stop) — **all six fail, and mostly on
the same mechanism**: with both rungs banked, a full stop-out at the never-raised floor settles
at EXACTLY `(1 + second_partial_r) / 3` R — 2.00R for a 5R second rung, 3.00R for 8R, 3.67R for
10R. That mechanical floor is why the ORB-low/8R and /10R cells show a *few* settled ≥3R names
(the arithmetic clears 3.0R) while every 0.5×ADR variant and the ORB-low/5R variant show **zero**
— this is an artifact of the formula, not organic price action, and is stated so it is never
quoted as a real tail finding.

| cell | settled admitted (n/≥3R/≥5R) | ex-May (n/≥3R) | settled+marks ≥3R (of which marks) | paired Δ≥3R (dropped) | verdict |
|---|---|---|---|---|---|
| adr_0.5, 2nd @5R | 49 / 0 / 0 | 38 / **0** | 5 (5 marks, 0 settled) | +0 (18) | fails |
| adr_0.5, 2nd @8R | 49 / 0 / 0 | 38 / **0** | 5 (5 marks, 0 settled) | +0 (18) | fails |
| adr_0.5, 2nd @10R | 50 / 0 / 0 | 39 / **0** | 5 (5 marks, 0 settled) | +0 (17) | fails |
| orb_low, 2nd @5R | 51 / 0 / 0 | 38 / **0** | 7 (7 marks, 0 settled) | +0 (15) | fails |
| orb_low, 2nd @8R | 51 / 5 / 0 | 38 / **2** | 11 (6 marks, 5 settled) | +5 (15) | fails ex-May (2<3) |
| orb_low, 2nd @10R | 51 / 4 / 0 | 38 / **1** | 10 (6 marks, 4 settled) | +4 (15) | fails ex-May (1<3) |

`t3` after the second rung (sell the remaining third at the 3rd close after the FIRST
partial) — **all six clear every leg of the pass bar**:

| cell | settled admitted (n/≥3R/≥5R/p90/med/sum) | ex-May (n/≥3R) | settled+marks (≥3R/sum) | drop-best | paired Δ≥3R (dropped) | verdict |
|---|---|---|---|---|---|---|
| adr_0.5, 2nd @5R | 55 / **8** / 4 / +4.45 / −1.00 / +28.3 | 44 / **6** | 9 / +31.8 | 9→8 | +8 (12) | **clears the bar** |
| adr_0.5, 2nd @8R | 55 / **10** / 5 / +4.84 / −1.00 / +33.9 | 44 / **7** | 11 / +37.4 | 11→10 | +10 (12) | **clears the bar** |
| adr_0.5, 2nd @10R | 56 / **10** / 6 / +5.27 / −1.00 / +33.6 | 45 / **8** | 11 / +37.2 | 11→10 | +10 (11) | **clears the bar** |
| orb_low, 2nd @5R | 59 / **12** / 4 / +3.58 / −1.00 / +34.0 | 46 / **8** | 13 / +38.0 | 13→12 | +11 (8) | **clears the bar** |
| orb_low, 2nd @8R | 59 / **13** / 5 / +3.68 / −1.00 / +39.2 | 46 / **9** | 14 / +43.2 | 14→13 | +12 (8) | **clears the bar** |
| orb_low, 2nd @10R | 59 / **12** / 4 / +3.58 / −1.00 / +39.5 | 46 / **9** | 13 / +43.5 | 13→12 | +11 (8) | **clears the bar** |

Regime split (all six, admitted settled): Bull holds most of the tail (e.g. orb_low/8R: Bull
n=37 ≥3R=10 sum +32.2, non-Bull n=22 ≥3R=3 sum +6.9) — same majority-Bull caveat as every other
number in this population (40 Bull : 25 non-Bull on the admitted 65).

Operator names, orb_low + 2nd@8R (the widest of the six, for illustration — all six are close):
PLTR +3.58R · TEAM −1.00R · HTFL +3.46R · MRNA +3.09R. **TEAM is stopped in every second-rung
cell** — the tight day-1 stop (entry−2R here is not in play; these are ORB-low/0.5×ADR, both
tighter than TEAM's actual $2.22-margin survival under the live entry−2R stop, design doc §2.1)
costs the operator's own named re-entry name on day 0. This matches the design doc's own §6 cost
line for the plain tight-stop cells ("TEAM stopped on day 0").

**Cost of the second rung vs. the plain (no second-rung) tight-stop × t3 cell already found by
Phase 3** (design doc §0, cited not re-run here: 0.5×ADR × t3 pays 10/5/+4.76R(p90)/+35.6R(sum)
on admitted 56; ORB-low × t3 pays 12/4/+3.58R(p90)/+40.1R(sum)) — **the cost is real but not
uniform, and not always a tail cost**:
- **At the lowest rung (5R), a SUM cost shows on both stop bases** — 0.5×ADR loses ~7R of sum
  and 2 of its 10 ≥3R names; ORB-low holds its ≥3R count (12) but still loses ~6R of sum. This
  is the pre-stated cost ("a second partial caps 1/3 of the runner at its rung," §7).
- **At 8R–10R the sum cost shrinks to ~1–2R and the ≥3R/≥5R COUNT is sometimes flat or slightly
  HIGHER than the plain cell** (ORB-low + 8R: 13 ≥3R vs the plain cell's 12; 0.5×ADR + 10R: 6
  ≥5R vs the plain cell's 5). **This is not noise** — a second rung locks in a name's gain at
  the moment it FIRST reaches that level; a plain single-partial `t3` instead carries the whole
  remaining 2/3 to the literal day-3 close, so a name that peaks above the rung and gives some
  of it back before day 3 scores WORSE plain than with the rung banking the peak. **The second
  rung is not a pure tail cost — it trades a small amount of sum for protecting some names
  against a give-back before the time exit fires**, and which of those two effects the operator
  weighs is exactly the fork this card surfaces, not resolves.

---

## Which cells clear the pass bar

**The pass bar, pre-stated (§7), applied as written:** a cell is a candidate ONLY if ALL hold —
(1) paired ≥3R on the admitted settled set ≥ live's + 3; (2) holds ex-May (same threshold, cohort
cut — the same convention the design doc uses throughout its own tables); (3) does not depend on
one name (drop-best); (4) settled+marks sum ≥ live's settled sum − 5R (i.e. ≥ −1.5R).

**Six cells clear all four legs — all six are `t3` after a second rung on a tight stop:**
`adr_0.5` + second-rung-5R/8R/10R, and `orb_low` + second-rung-5R/8R/10R, each riding `t3`
(sell the last third at the 3rd close after the FIRST partial). **Ten cells fail, in three
groups:** (a) **6 hit zero settled ≥3R names** — `stop + hold`, `hard` (no second rung), and 4
of the 6 `hard` second-rung cells (`adr_0.5` at 5R/8R/10R, `orb_low` at 5R) — every one of these
triggers the "what would kill it" check below; (b) **2 more `hard` second-rung cells**
(`orb_low` at 8R/10R) settle a handful of ≥3R names via the mechanical `(1+R2)/3` floor
described above but still fail the ex-May leg (2 and 1 names, short of +3); (c) **2 fail on the
ordinary +3 margin without hitting zero** — `stop + trail only` (ex-May count 2, one short) and
`partial, no breakeven, trail stays` (paired Δ≥3R +1, two short).

---

## What would kill it — checked as pre-registered

*"if no-breakeven cells only move MARKS and never settle a ≥3R name by the horizon, then the
tail is a mark and not a return — say so plainly."*

**True for `stop + hold` and `hard` (no second rung): both show ZERO settled ≥3R names in every
cut (all-alerts, admitted, ex-May) — every ≥3R name either is an open mark or never appears.
This is a mark, not a return, and neither cell is a candidate under the pass bar for exactly
that reason** (criterion 1 alone kills both: paired Δ≥3R = 0). Five of the six `hard`
second-rung cells repeat this pattern; the other one (`orb_low` + 8R) clears the settled-≥3R
threshold ONLY via the mechanical `(1+R2)/3` floor described above, and still fails on the
ex-May leg. **The `t3` second-rung cells do NOT hit this failure mode**: 8–10 of their 9–14
total ≥3R names are SETTLED (not marks) even before ex-May is applied — `t3` forces a sale at a
fixed calendar point, so it settles instead of riding indefinitely into `open_at_horizon`.

---

## What this does not answer

- **Whether any of the six clearing cells survives the fill minute.** These are replay
  populations at daily/1-minute grain; #482's live-fill counterfactuals (`stop_adr_050` reads
  −0.661R on 6 real fills, the WORST arm on night one) is the only forward evidence and it
  points the opposite direction at n=6 — nowhere near enough to settle anything, but stated
  because it disagrees.
- ~~**The currently-deployed stack (era D) is a DIFFERENT experiment from the one this grid
  measures.**~~ ✅ **RUN — see the CORRECTION section above. The era_d baseline was measured and
  it changes the result from six clearing cells to five.** The original note read:** This card's baseline and every
  cell in it is built on the pre-09-06 2R-partial ladder, matching the design doc's own
  convention and the reused-cell list this card was scoped against. A second-rung sweep against
  the era-D 8R-partial baseline would be a different, not-yet-run grid.
- **Whether the second rung should sit at 5R, 8R or 10R, or whether `t3`, `hard` or the live
  ladder should govern what's left after it fires.** The grid shows the shape of the trade-off
  (a lower rung books earlier and costs more tail; `t3` settles, `hard` does not); it does not
  pick a level — that is the operator's, under CHANGE_PROCESS.
- **Day-0 intraday second-rung fires** (both rungs inside the entry-day minute bars) — scoped
  out of this card's code change (stated above); a rare edge case for a 5R+ move on entry day,
  not expected to move these totals, but not measured.
- **Portfolio interaction** — slot competition, the 2% daily-loss limit, the count breaker.
  Every campaign here is priced alone, same limitation as every P-REPLAY number in the design
  doc.
- **The population gap** (§5.1 of the design doc: `stop_too_wide` refusals, pre-05-11 alerts,
  scan-level skip buckets, post-08-28 alerts, the 44 float-undecided admissions, the 46
  abstains) — none of it is in this grid; Phase 2 of the design doc's plan is what closes it.
- **Concentration beyond drop-best-one.** The `t3` cells spread their tail over 7–13 names each
  (FTK, INFQ, QBTS, ARGX, HTFL, ABCL, PLTR, MRNA, CRWD, CLF, QUBT, RDW, U, ZBRA, NBIS, EROC
  appear across the six) — comfortably not single-name-carried — but a two-name-drop or
  three-name-drop check was not run.

---

---

## ⚠ CORRECTION, 2026-09-22 — THE BASELINE WAS THE WRONG ERA, and the result changes

Everything above is measured against **`era_c`** (2R partial, breakeven at partial), which the
design doc calls "live". **It is not live.** Prod flipped to **`era_d`** on 2026-09-06
(`b52fdcbc`: partial moved to **+8R**, price-armed breakeven at **+3R**) — sixteen days before
this card ran. A cell that beats a RETIRED ladder has not been shown to beat the one we run, and
that is this repo's most expensive recurring mistake. [[check-the-rule-era-before-comparing-to-actual]]

Re-run through the card's OWN probe module, so the population, admission and walk are identical
(`scripts/probes/_545_phase1_era_d_baseline.py`; 267 campaigns; paired on the 65 rows settled
under both eras):

| baseline | n | ≥3R | ≥5R | sum | ex-May ≥3R |
|---|---:|---:|---:|---:|---:|
| `era_c` — the card's baseline, **RETIRED 09-06** | 65 | **0** | 0 | +3.5 | 0 |
| **`era_d` — LIVE since 2026-09-06** | 65 | **5** | 1 | **+12.1** | 3 |

**The live ladder does not settle zero ≥3R names. It settles five** — ARGX, FTK, INFQ, QBTS and
**TEAM**. So the headline above ("+8 to +12 over the live ladder's 0") is wrong as written; the
true comparison is against 5.

🔑 **That is also a result about HIS OWN 09-06 FLIP, which nothing had measured on this
population: it is worth ~+8.6R of sum and five ≥3R names against the rule it replaced.**

### The pass bar re-applied against `era_d` — bar becomes ≥3R ≥ 8, ex-May ≥ 6, sum ≥ +7.1R

| cell | ≥3R | ex-May | drop-best | sum | verdict |
|---|---:|---:|---:|---:|---|
| `adr_0.5` + 2nd @5R | 8 | 6 | 7 | +30.3 | **FAILS** — drop-best 7 < 8 |
| `adr_0.5` + 2nd @8R | 10 | 7 | 9 | +35.9 | clears |
| `adr_0.5` + 2nd @10R | 10 | 8 | 9 | +35.6 | clears |
| `orb_low` + 2nd @5R | 11 | 7 | 10 | +30.2 | clears |
| `orb_low` + 2nd @8R | 12 | 8 | 11 | +37.1 | clears |
| `orb_low` + 2nd @10R | 11 | 8 | 10 | +37.4 | clears |

**FIVE cells clear against the live rule, not six** — `adr_0.5` + 2nd @5R drops out on drop-best
once the bar rises. And the margin is **+3 to +7 ≥3R names over live, not +8 to +12.**

⚠ **AND THE LIVE RULE KEEPS A NAME THE CANDIDATES LOSE: `era_d` settles TEAM at ≥3R, while TEAM
is stopped on day 0 in every second-rung cell** (both use a tighter stop than `entry−2R`). That
is a real cost against one of the four operator-labelled names, and it is not visible at all in
the era_c comparison, where live settles nothing.

**The finding survives the correction — smaller, and now stated against the rule we actually
run.** Nothing else in this document changes: the arithmetic-floor artifact, the kill-it check,
the regime concentration and every limit below stand as written.

## ⚖ THE LINE

Nothing here changes a stop, target, partial, trigger, re-entry rule, sizing or any live table.
No prod query was run; every input is a capture already in the repo. The six cells that clear
the pass bar are candidates for the forward gate (#482), not a recommendation — which R level,
which post-second-rung runner, and whether to touch the currently-deployed era-D stack at all
are the operator's, under CHANGE_PROCESS, the #151 harness, and his sign-off.

---
*Sources: `scripts/probes/_545_phase1_harvest_sweep.py` (this card, new) →
`_545_phase1_harvest_sweep_out.txt` (full run, every number above) and
`_545_phase1_harvest_sweep.tsv` (4,539 campaign rows, per-cell). Code:
`scripts/ep_replay.py` (`RuleSet.second_partial_r`, `_walk_leg`). Tests:
`tests/test_ep_replay.py` (44/44 pass). Prior work, cited not re-derived:
`docs/design/545_entry_exit_program_2026-09-05.md` §0, §1, §7; `_545p3_cells.tsv` /
`_545v3_tail_rank_out.txt` (the numbers this card's LIVE baseline and the plain-tight-stop×t3
comparison are checked against, and matched). `docs/methodology/analysis_standard.md`,
`operator_labelled_eps.md`, `ANALYSIS_CARD_PREAMBLE.md`. `scripts/live_rules.py` output,
2026-09-22 07:30 PDT.*
