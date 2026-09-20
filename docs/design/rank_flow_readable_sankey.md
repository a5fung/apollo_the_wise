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
| data gap — row present, rank null | 2 | 10% |
| returning — ranked before, absent, back now | 0 | 0% |

**Consequence in one line: the fattest ribbon on the chart is real. Climbing out of "No rank" is
almost always a theme being BORN, not our snapshot filling a hole.**

**RULING (operator, 2026-09-19): do not split the band — RENAME it "New / unranked".** Splitting
would add a sixth band to a 390px screen to separate a 2-cohort case from an 18-cohort one. The
honesty stays cheap and stays in the caption: when the data-gap share is unusual, the caption says
*"2 of 20 were data gaps"* rather than the geometry carrying it.

⚠ **Stated limit: 19 weeks of history.** A theme first ranked before April 2026 reads as "brand
new" here, which inflates the 90%. Treat the 10% data-gap share as a FLOOR, not a ceiling.

### Still open

Nothing blocking. The build is a normal card: `theme_flow.render_flow` gains the vertical
two-column layout, the sentence header, and the band rename; `compute_band_flow` already returns
exactly the shape this needs and does not change.

