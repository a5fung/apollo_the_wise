# CHART STRUCTURE — the operator's model, and what is encoded

**SSoT for structure. Read this before touching anything structure-related** — the encoder, the
grade, a "does structure predict X" question, or any proposal to add a structure feature.
Created 2026-08-16 at his instruction: *"make sure to capture this conversation as context going
forward on structure."*

His bottom line, and the reason this file exists: **"I believe price/chart structure is key
ingredient to EP."**

---

## 1. THE MODEL, in his words (2026-08-16)

> "At the end of the day, structure shows historical prices, and congestion of prices is where
> potential supply is (in theory, that's where lots of buy/sell happened, and where ppl may be
> holding stock at that price and maybe will be willing to sell it there to breakeven or whatever
> reason), and each supply point / pivot it passes, the stock has chance to move to the next supply
> zone until it's all clear and where the stock has blue sky potential. Of course, there's lots of
> nuance, like how far back to look etc. and this is where concepts like basing, etc. comes in."

> "EPs that clear congestion zones the more it clears the stronger all else equal. If the gap up
> just meets the first congestion or fails even to go above it is iffy, the same concept of moving
> averages, it's just any proxy or gauge to see how strong the gap up is aside from raw % which has
> no reference. Gapping up above key levels, holding, even pulling back to not failing is sign of
> strength."

**Decomposed — the five claims, each separately checkable:**

1. **Congestion = potential supply, and the mechanism is HOLDERS.** Volume traded at a price means
   people own stock there, and many will sell at breakeven. A level rejects price because sellers
   live there. This is a supply argument, not a chart-pattern argument.
2. **It is a LADDER, not a gate.** Each pivot cleared buys a run **to the next supply zone**.
   Structure therefore predicts **how far a move can travel**, not merely whether it goes up.
3. **Blue sky is the limiting case** — nothing overhead, the stock is free.
4. 🔴 **Raw gap % has NO REFERENCE FRAME; zones-consumed does.** The count of congestion zones a
   gap clears is the gauge. More cleared = stronger, all else equal.
5. **HELD, not touched.** Clearing a level, holding it, and pulling back *without failing* is the
   strength signal. A poke through that is lost is weakness.

**Corollaries he stated:** the IFFY case is a gap that stalls at, or fails to exceed, the FIRST
congestion — its own bucket, not a low score. Moving averages are *"the same concept… just another
proxy or gauge"*. And basing belongs here: a base IS a congestion zone the stock has already
absorbed, which is why *"a decent looking base"* was one of his four SE conditions.

### Why this resolves the plan's central contradiction

Gap size ranks BACKWARDS in our own data — **BW gapped 34.9%** at the bottom of the RS field and
died inside 60 seconds, while **PLTR (16.0%)** and **EROC (16.1%)** are his two labelled good EPs.
Same signal, opposite meaning. Under this model that is not a paradox: percent was never the
measurement. **If zones-consumed beats gap % at comparable gap size, gap is not merely
over-weighted in the grade — it is measured in the wrong unit.**

---

## 2. THE FALSIFIABLE DEFINITION (NBIS, 2026-08-12) — what "good structure" means

His first definition precise enough to be wrong:

- **Clears a level that previously REJECTED price** (on NBIS: the 50-day, and prior highs ~$227),
- **then HOLDS it after the first pullback.**
- **Failure classes, both named by him:** cleared-then-lost-it · never-breached-at-all.
- **The complaint it answers:** *"some of the trades we make it just gaps into congestion,
  resistance areas and had no strength to break through it."*

---

## 3. WHAT IS ENCODED TODAY

`scripts/probes/_533_nbis_structure_encoder.py` — **SHADOW ONLY**; it is wired into nothing, and it
refuses to sweep a population unless the fixture gate below passes. Capture:
`docs/analysis/structure_encoding_2026-08-15.txt`.

**Level derivation (the part that answers "part science, part art"):**

1. Levels are daily pivot highs merged within **0.3%** (his own RMV-developer parameter,
   2026-06-30), qualified only by **≥2 failed test EPISODES** — a test approaches within 0.5×ADR20
   and fails to close above; two tests count separately only if a ≥1×ADR20 rejection lies between
   them, so chop hugging a line is ONE test. A daily close above the level kills it.
2. 🔴 **The lookback is each level's own test dates — there is no window parameter.** Levels reach
   back exactly as far as their failed tests do (NBIS's to July, SE's base to February, HTFL's ATH
   pair to last October). This is his objection to fixed lookbacks made mechanical, and it is the
   thing a moving-average proxy can never express.
3. The 50-day counts only when it has ≥2 failed episodes in the current below-SMA regime; the
   52-week/ATH "nothing overhead" case is its own class; a single untested ATH print is never
   counted as congestion.

**⚠ Three thresholds are fixture-calibrated** and disclosed in the probe header: the opening-drive
breach window (through 09:59), the 0.25×ADR through-not-onto margin, the 70% deep-in-downtrend veto.
**The fixtures are the CALIBRATION set, not a test of the encoder.**

---

## 4. THE FIXTURE GATE — his eight labelled reads, and it must keep passing

**Any structure change must reproduce these before it is trusted.** Passed 8/8 on 2026-08-16.

| Name | Date | His call | Why (the encoder's reason, which matched his) |
|---|---|---|---|
| NBIS | 08-12 | GOOD | cleared + held a level derived at **$226.81** — his own "~$227" |
| HTFL | 08-14 | GOOD | cleared + held 39.24, the old ATH region, no recent overhead |
| ETON | 08-14 | GOOD | blue sky — opened above every prior high, and held |
| EROC | 08-12 | GOOD | cleared + held its 6-test base top 11.88 ⚠ only 43d of history |
| SE | 08-11 | GOOD | cleared + held base top 118.09; the January $129 shelf shows as 0.28 ADR of remaining overhead — **exactly where it stalled** |
| **VERA** | 08-14 | **POOR** | poked 31.8 and lost it · 88.3% of last-60 closes above the open · below the 20- and 50-day |
| BW | 08-11 | POOR | cleared then lost everything; never gapped over its 50-day |
| FRMI | 08-11 | POOR | landed ON its 50-day (7.07 open vs 7.06) |

📌 **VERA is the case that matters** — a gap that looks fine and is structurally weak. Anything that
calls VERA good is measuring "it went up", not structure.

---

## 5. WHAT IS *NOT* ENCODED — named honestly, so nobody claims coverage

- **Stage analysis** (*"possibly moving to a Stage-2 uptrend after bottoming and basing"* — his SE
  condition 3). No classifier exists. Named in the notes as the biggest of the four SE gaps.
- **Group / theme strength** (*"retail group is strong where this belongs"* — SE condition 4).
  Outside a price-level definition; it is #563's territory, and SE was in NO live theme at all.
- **Basing quality** beyond "a level was absorbed" — *"decent looking base"* is still a shape
  judgement with no number.
- Alerts before 2026-07-28 have no minute bars, so no hold leg — they run in a labelled
  degraded open-only tier.

---

## 6. ⛔ THE REJECTED PROXY — do not re-propose it

**"Price above all three SMAs" (plus a fixed-lookback high-clear) was tested, returned a null, and
was rejected by him** (2026-08-12): *"i don't necessarily agree here… chart structure is part
science part art… The better way to see this is probably to have a few winners to compare it
with."* Two lessons, both paid for:

- A fixed lookback cannot express his model; the lookback must come from where the tests are.
- **Hunting for separation inside a cohort with zero winners cannot work.** The 08-15 population
  sweep (357 alerts, 273 encoded) was null at p=0.74 for exactly this reason — and that is the
  result he predicted, not a verdict on structure. The encoder's real test is the **winner
  reference set**, not our own losing cohort.

---

## 7. ⚠ THE FIRST LADDER TEST CAME BACK BACKWARDS (2026-08-16)

`scripts/probes/_533_supply_ladder_probe.py`, output `docs/analysis/structure_ladder_2026-08-16.txt`.
Population = alerts we DECLINED (`mi_ep_missed_outcomes`), 2026-05-11 → 08-14.

**His decisive test — `zones_cleared` vs raw gap % — is a draw, and NEITHER survives correction.**
0 of 15 pre-registered tests clear multiplicity adjustment. Binary 0-vs-≥1 zones cleared:
−1.9pp on 5-day max excursion (n=374/116, 83/62 sessions, raw p=0.25). Gap % median split:
+2.0pp, raw p=0.19. So on this evidence gap % is **not** displaced by zones-consumed — but neither
is it vindicated.

🔴 **The graded dose table runs the WRONG WAY, monotonically:** median 20-day max excursion falls
**18.7% → 17.5% → 12.1% → 11.2%** as `zones_cleared` goes 0 → 1–2 → 3–5 → 6+. Spearman −0.11 to
−0.14 for zones_cleared against both horizons, versus ~0 for gap %. **And the blue-sky bucket —
his model's limiting case — is the WEAKEST, not the strongest:** n=122, median 5-day excursion
**8.9%** against **11.3%** for names with overhead (raw p=0.14).

### Three readings, and the third is the one worth acting on

1. **Nothing is significant.** 0 of 15 survive adjustment; formally there is no finding here, and
   that has to be said before any story is told about the gradient.
2. **ADR is a real confound and it is only partly excluded.** Zones are measured in ADR units, so a
   LOW-volatility name has many closely-spaced zones and clears several on a modest move, while a
   high-volatility name has few. Measured: rho −0.35 zones-vs-ADR, +0.36/+0.38 ADR-vs-excursion.
   The backwards gradient survives inside the low-ADR half and goes flat in the high-ADR half
   (cells as thin as n=23) — so it is not purely a volatility artifact, and not uniform either.
3. 📌 **We may be measuring from the wrong origin, and this is consistent with HIS model rather
   than against it.** Excursion is measured **from the alert-day open** — i.e. AFTER the gap has
   already consumed the structure. A name that has cleared six supply zones has spent that travel;
   what remains is by definition the *rest* of the move. His ladder describes **potential from
   where the move STARTS**, not from where our alert fires. On that reading a negative gradient is
   what you would expect, and the test that matches his model would measure remaining overhead
   from the ENTRY, and travel to the NEXT zone — not zones already behind it.

⚠ **This population is alerts we DECLINED, never entered** — it says nothing directly about our own
trades. And per §6, an all-losing cohort is the wrong place to learn what good structure is worth.

▶ **Not a refutation of the model. It is a refutation of THIS operationalisation of it** — and the
open question below is re-pointed accordingly.

## 8. THE OPEN MEASUREMENT

**`zones_cleared` head-to-head against raw gap %, at comparable gap size**, against
excursion SIZE (max favourable move) as well as direction — because his model says structure
predicts how far a move travels, and excursion is measurable even in names that ended as losers.
This is the first structure feature that speaks to the **W** term of the goal arithmetic (average
winners must exceed 4R) rather than the win-rate term.

Related: the MAs-cleared count as a cheap parallel gauge · the IFFY bucket reported separately ·
zones cleared **and held** as the strength measure.

---

**Pointers:** `docs/methodology/operator_shared_notes.md` (dated verbatim captures — 08-11 SE,
08-12 NBIS + the reframe, 08-14 HTFL/ETON/VERA, 08-16 the supply-ladder model and the
zones-cleared refinement) · `docs/roadmap/ep_profitability_program.md` §2 and the dated sections
for the encoder, PLTR and EROC · fork **S-3** is the only route to promoting any of this into the
grade, and it needs CHANGE_PROCESS plus his sign-off. 🛑 Structure work is SHADOW until then.
