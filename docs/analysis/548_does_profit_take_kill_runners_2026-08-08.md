# Does the +2R profit-take kill the big winners? — replay, 2026-08-08

**EVIDENCE ONLY. No rule changed, nothing proposed. Exit discipline is THE LINE.**

## The operator's framing, which is the right test

> *"EP is rare and our goal is to catch the big outsized winners and lose little for the larger
> number of losers. With profit take strategy, it doesn't change the goal — we're not trying to
> 'win' by making many tiny profits… the profit take is mainly to stop the papercuts, not being
> bled out by too many small losses that will erase the big win. The goal remains to catch the
> big wins while limiting losses… if this +2R and especially breakeven stops ends up killing our
> chance of big winners, then it would have failed its goal."*

So the rule is not judged on mean R. It is judged on **whether it preserves the runner while
cutting the papercuts.** That is what this replay measures.

Harness: `scripts/probes/_508_exit_rule_replay.py`, offline, $0.
⚠ Snapshot is 2026-08-01 — **12 live trades, not today's 17; FIGS is not in it.**

## Q1 — with the fix, do the trades that reached +2R become winners? YES.

| trade | peak | actual | with the fixed rule (1/3 @ 2R + breakeven) |
|---|---|---|---|
| MANE | +7.92R | −0.23R | **+0.67R** |
| SMCI | +3.21R | −0.70R | **+0.67R** |
| NVCR | +2.00R | −1.00R | **+0.67R** |
| QBTS | +3.74R | −1.00R | **+0.67R** |

Live cohort mean: doing nothing **−0.92R/trade** → the rule **−0.46R/trade**.

## Q2 — but look at the ceiling. This is the operator's point, in the data.

**Every one lands on EXACTLY +0.67R.** MANE reached **+7.92R** and keeps the same +0.67R as NVCR,
which barely tagged 2.00R. The excursion is irrelevant to the outcome.

That is not a coincidence, it is arithmetic: 1/3 × 2R = 0.67R banked, and the remaining 2/3 exits
at breakeven for zero **whenever price returns to entry**. On the live cohort it always did —
which is the same fact as *reached avg +1.54R → kept −0.91R*. **Nothing in this cohort has ever
held a gain.**

⚠ **So the live cohort CANNOT answer "does breakeven kill runners" — it has never had a runner
that held.** The paper cohort has.

## Q3 — on trades that DID run and hold, what does the rule cost? A fixed ~0.67R, not the winner.

| trade | peak | do nothing | 1/3 @ 2R + BE | cost |
|---|---|---|---|---|
| BW | +10.16R | +4.06R | **+3.37R** | −0.69R |
| GOOGL | +8.18R | +4.02R | **+3.35R** | −0.67R |

**The breakeven stop did not take them out.** A genuine runner does not come back through entry,
so the stop never fires; the only cost is the third sold early. BW keeps 83% of the do-nothing
outcome, GOOGL 83%.

And on the runners that gave it all back, the rule is the difference between a win and a loss:

| trade | peak | do nothing | 1/3 @ 2R + BE |
|---|---|---|---|
| CRSR | +12.36R | −0.01R | **+0.67R** |
| RCAT | +5.24R | −0.02R | **+0.67R** |
| FTRE | +5.40R | −0.17R | **+0.67R** |

## Q4 — WHERE the danger actually lives: the trigger LEVEL, not the breakeven itself

This is the sharpest number in the replay, and it validates the operator's instinct precisely —
it just locates the risk one step to the left of where the question put it.

| GOOGL (peak +8.18R) | kept |
|---|---|
| do nothing | +4.02R |
| **1/3 @ 1R + breakeven** | **+0.33R** |
| **breakeven only, armed at 1R** | **+0.00R** |
| 1/3 @ 2R + breakeven | +3.35R |

**Arming breakeven at +1R destroys the entire +8.18R winner.** At +2R it survives. The mechanism
that kills runners is arming the breakeven stop *before the trade has cleared its own noise* — a
+1R move is inside ordinary intraday range, so price revisits entry and scratches the position out
of a move that had 8R in it.

**+2R sits above that danger on this evidence.** That is a reason to be careful about ever
lowering the trigger, not a reason to distrust the current one.

## Q5 — the variant that WOULD fail his test

**Exit ALL at 2R**: BW +10.16R peak → **+2.00R flat**. GOOGL +8.18R → +2.00R. CRSR +12.36R →
+2.00R. It scores well on mean R across the cohort *precisely because* it converts every runner
into the same small win — the "win by many tiny profits" outcome he explicitly ruled out as the
goal. **Recorded here so it is never adopted on a mean-R argument.**

## Verdict against his stated goal

- **Papercuts: cut.** Four −1R losses became +0.67R.
- **Big winners: preserved, at a fixed ~0.67R toll.** Not capped, not destroyed.
- **The rule has NOT been shown to preserve a LIVE runner**, because the live cohort has never
  produced one. That evidence is paper-only and must be labelled as such.
- **The failure mode he named is real, and it lives at the trigger level.** At +1R the rule does
  exactly what he feared. At +2R it does not.

## Open, not decided

`ADR1_part1/3+BE` (trigger at 1× the stock's own 20-day ADR rather than a fixed R multiple) scores
**best on the live cohort: −0.23R vs −0.46R** for the fixed +2R. It directly addresses the earlier
finding that *R is not a fixed unit* — live stop widths span 0.14×–0.97× of the ticker's own ADR,
so a fixed-R trigger fires constantly on tight-stopped names and never on wide-stopped ones.
**Surfaced, not proposed.** It is a criteria change and belongs to CHANGE_PROCESS + sign-off.

## Honest limits

- 12 live trades, **zero live winners** — every "gain" here is loss-reduction, not profit.
- The runner-preservation result rests on **two paper trades** (BW, GOOGL). Two.
- Snapshot predates FIGS, TEAM, NET, BLZE, BTDR.
- The replay assumes the FIXED mechanism (limit fill AT the 2R level, real-time breakeven). The
  currently deployed mechanism does neither — see #548 — so these numbers describe the rule as
  intended, not as it presently runs.

---

## Addendum — "where does a true runner sell?" (operator, 2026-08-08)

**The mechanism you're thinking of is real: a close below `max(SMA10, SMA20)`.** Not SMA10 alone
— the trail takes the HIGHER (tighter) of the two, evaluated **once a day against the close**
(`exit_logic.py`, `trail_mode="sma"`, the deployed default). Nothing in the exit path sees
intraday price, so it is a close-only decision.

So a runner's full ladder is:

1. **+2R intraday** → sell 1/3, arm breakeven. *(New on 2026-08-01. The only intraday mechanism.)*
2. **Breakeven stop** on the remaining 2/3.
3. **Close below max(SMA10, SMA20)** → trail out. **Needs ≥10 daily closes to exist at all.**
4. *(Day 3-5 partial — being replaced by (1).)*

### ⚠ On live money, step 3 has never happened and currently cannot

| | live | paper |
|---|---|---|
| closed trades | 17 | 34 |
| average hold | **0.1 days** | 3.8 days |
| longest hold | **2 days** | 23 days |
| ever reached day 10 | **0** | 5 |
| `sma_trail_stop` exits | **0** | 2 |

Live exit reasons, all 18 legs across 17 trades: **17 × `stop_hit`, 1 × `partial_profit`.** The
moving-average trail is not a rule the live book has ever been subject to — it is a rule the live
book has never survived long enough to reach.

**So the honest answer to "where does a true runner sell": on live money, nowhere — there has
never been a runner.** The trail is the designed answer and it is currently theoretical. It has
fired exactly twice in the system's history, both in paper.

This reframes the +2R discussion: today the +2R partial is not competing with the MA trail for a
runner's profit, because the trail has never had a trade to act on. It is competing with
`stop_hit` at −1R.

⚠ It also means the runner-preservation evidence in this document is **entirely paper-derived**,
and paper is the only cohort where trades live long enough for a trail to matter.
