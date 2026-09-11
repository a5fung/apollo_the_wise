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
