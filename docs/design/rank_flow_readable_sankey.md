# Rank Flow — the readable-Sankey target (operator reference, 2026-09-11)

**Trigger.** He looked at the repaired Rank Flow and said *"still not readable, can this view even
be fixed?"*, then sent his own Income → Expense Flow chart from the same dashboard and said
**"what I really want is a sankey chart like this which is readable."** Reference image saved at
`docs/design/reference/sankey_readable_operator_2026-09-11.png` — captured because chat images are
lost and this one is the spec.

## Why HIS chart is readable and Rank Flow is not

The difference is not styling. It is the shape of the data being drawn.

| | his expense flow | Rank Flow today |
|---|---|---|
| columns | **3** (income → category → leaf) | **11** (one per week) |
| flows | a **tree** — each node has one parent | a **many-to-many transition matrix**, every week |
| nodes | ~8 categories, ~20 leaves | 5 bands × 11 weeks = 55, carrying 142 cohorts |
| labels | every node names itself **with its value and share** — *"Financial $4,135 24%"* | bands named, flows anonymous |
| crossings | almost none | hundreds |
| the question it answers | *where did the money go* | *(intended)* which theme is climbing |

**A tree with 3 columns is legible at a glance. A transition matrix over 11 periods is not, at any
opacity or palette.** That is why the colour and label work (#640, shipped 2026-09-11) made it
correct without making it readable — it fixed a lie in the data, not the density.

## What to build instead

**ONE transition, decomposed like his chart — not eleven.**

- **Left column:** last week's bands (Top 5 · 6-15 · 16-30 · 31+ · No rank).
- **Right column:** this week's bands.
- **Every node labelled with its own count and share**, exactly like *"Financial $4,135 24%"* —
  e.g. *"Top 5 · 5 cohorts · 4%"*. Today's bands carry no number at all.
- **Ribbons labelled where they matter**: the few cohorts that CHANGED band get named; the
  stay-put ribbons are one grey band with a count, not individual flows.
- The week is **pickable**, so eleven weeks are eleven readable charts rather than one unreadable
  one.

**Open question for him, not to be pre-decided:** whether the left column should be *last week* or
*N weeks ago* (a 4-week hop shows more movement and fewer ribbons). His chart has no time axis at
all, so there is no precedent to copy here.

## What this replaces

Nothing yet. The current view stays as-is (correct, dense) until the redesign ships — he asked for
it ON HOLD, not deleted, and #561 already tried deleting it once and he asked for it back.

---

## MOBILE PASS + OPERATOR SIGN-OFF — 2026-09-19

He asked for a mockup he could look at. Built at true 390px and rendered from the live grid:
**https://claude.ai/code/artifact/6d31c493-5f81-4b48-bf74-c7b366162581**

### The number that settles the layout

Measured on the live canonical weekly grid (1,895 rows, 24 weeks):

| view | cohorts | ribbons | moved | held | movers |
|---|---|---|---|---|---|
| today — all 24 weeks | 218 | **357** | 734 | 335 | 69% |
| 1-week hop | 48 | 17 | 41 | 7 | 85% |
| **4-week hop (chosen)** | 55 | **17** | 52 | **3** | **95%** |
| 8-week hop | 60 | 11 | 60 | 0 | 100% |

⚠ **This corrects an assumption in the section above.** The 09-11 doc treated stay-put ribbons as
the boring bulk to collapse into one grey band. In a SINGLE transition they are **3 of 55**. The
clutter was never the stayers — it was drawing eleven weeks at once. Collapsing them is still
right, but it is a detail, not the fix.

### Agreed, 2026-09-19 (operator: *"Aligned"*)

1. **Vertical, not horizontal.** Phones are tall. Side-by-side columns leave ~120px of ribbon
   between two label stacks at 390px; flowing top-to-bottom gives labels the width.
2. **Four-week hop by default** — the open question the 09-11 doc left for him. Same 17 ribbons as
   one week, 95% movers against 85%.
3. **The answer in a sentence above the chart** — *"25 climbed · 27 fell · 3 held"*, then the
   biggest single move by name.
4. **Tap, never hover.** Counts and shares are permanently on the chart (*"16–30 · 15 · 27%"*).

### The "No rank" band — MEASURED, and the answer is rename, not split

The 09-11 split (31+ vs No rank) fixed the four-way merge. What remained was whether *never-seen*
and *data gap* inside "No rank" are distinct enough to separate. **Measured over the chosen
2026-08-17 → 09-14 hop, on the 20 cohorts that left the band:**

| cause | n | share |
|---|---|---|
| **brand new — never ranked in 19 weeks of history** | **18** | **90%** |
| ~~data gap~~ → **engine-retired: row present, rank null** | 2 | 10% |
| returning — ranked before, absent, back now | 0 | 0% |

**Consequence in one line: the fattest ribbon on the chart is real. Climbing out of "No rank" is
almost always a theme being BORN, not our snapshot filling a hole.**

**RULING (operator, 2026-09-19): do not split the band — RENAME it "New / unranked".** Splitting
would add a sixth band to a 390px screen to separate a 2-cohort case from an 18-cohort one. The
honesty stays cheap and stays in the caption: when the data-gap share is unusual, the caption says
*"2 of 20 were listed but unscored"* rather than the geometry carrying it.

⛔ **"DATA GAP" WAS THE WRONG LABEL — corrected the same day, during the build.** I called those two
a data gap and told him to treat 10% as a floor on missing data. **Both were stage Retired**, and
measuring the whole snapshot settles it: **all 798 null-rank rows are Fading (424) or Retired
(374); not one is Nascent, Accelerating or Mainstream. There are NO data gaps.** A null rank is the
ENGINE'S VERDICT that a theme is done — so the floor was a floor on nothing, and `theme_flow.py`'s
module docstring, which called it *"a fact about our DATA, not about the cohort's strength"*, had
it backwards for eight days. Corrected there in the same build.

⚠ **AND THE TWO DIRECTIONS ARE NOT THE SAME THING.** *Leaving* the band is 90% a theme being BORN.
*Entering* it is the engine giving up on one: of the 14 that fell in over this hop, **7 vanished
from the snapshot and 7 are still listed but unscored — 5 Retired, 2 Fading.** So a ribbon INTO
that band is a real demotion, not an absence of data, and it is coloured directionally rather than
grey. The caption carries the listed-but-unscored count per hop.

⚠ **Stated limit: 19 weeks of history.** A theme first ranked before April 2026 reads as "brand
new" here, which inflates the 90%. Treat the 10% data-gap share as a FLOOR, not a ceiling.

### Still open

Nothing blocking. The build is a normal card: `theme_flow.render_flow` gains the vertical
two-column layout, the sentence header, and the band rename; `compute_band_flow` already returns
exactly the shape this needs and does not change.

---

## Multi-column Sankey — RAISED AND DECLINED, 2026-09-19

He asked whether to extend to 3 or 4 columns to track a longer period, flagging that it also
complicates the list underneath. **Ruling: *"leave as is for now."*** Recorded so it is not
re-litigated from scratch.

### Measured, on the live grid

| shape | span | ribbons |
|---|---|---|
| 2 columns (today) | 4 wks | **17** |
| 3 columns | 8 wks | 36 |
| 4 columns | 12 wks | 52 |
| 5 columns | 16 wks | 62 |
| **2 columns** | **12 wks** | **9** |
| 2 columns | 16 wks | 7 |

**A longer SINGLE hop gets CLEANER as it reaches further back (17 → 11 → 9 → 7); more COLUMNS get
denser (17 → 36 → 52 → 62).** Twelve weeks costs 9 ribbons as one hop and 52 as four columns —
four times the ink for the same span.

### The structural reason, which outranks the density one

**A Sankey cannot draw a path across 3+ columns.** Ribbon A→B and ribbon B→C are separate marks;
nothing in the picture says which cohorts in the first continue into the second. Over 3 columns
the grid carries **32 distinct paths against 36 ribbons** — the drawing and the journeys do not
even correspond.

This is the same point the top of this document makes about his expense chart: **that chart is a
TREE — one parent per node — so the path IS the geometry.** Rank flow is a many-to-many transition
matrix, and no amount of column-adding changes that.

### What each shape actually answers

- **One long hop** — *where is this cohort now versus then.* Net displacement. ⚠ A round trip
  (out of a band and back) reads as "held".
- **Multi-column** — *what was the path*, which is precisely what the geometry cannot show.
- **`theme_bump.py`** — one line per cohort, rank over time, identity preserved across weeks.
  **The path question already has a chart, and this is it.**

### If it is revisited

Make the hop length a control on the existing two-column view (4 / 8 / 12 weeks) and send "what
was the journey" to the bump chart. Do not add columns.

⚠ **The open question I could not close, and the honest weakness in the recommendation:** net
displacement hides churn, and **nobody has measured how often a cohort leaves a band and returns**
within a hop. If round trips are common, the one-hop view is understating movement. Worth knowing
before this is settled for good — not filed as a board line on his "leave as is".

