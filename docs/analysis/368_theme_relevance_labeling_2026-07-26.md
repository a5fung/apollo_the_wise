# #368 — theme-relevance labeling (operator ground truth)

**Sheet: `docs/analysis/368_labeling_sheet.tsv`** — 190 rows, opens in Numbers/Excel/any spreadsheet.
Fill the **LABEL** column (and NOTE where useful). Nothing else needs to change.

Estimated **1–1.5 hours** at ~20–30s a row. It does not have to be one sitting — the sheet is
resumable, and re-running the seeder never overwrites a row you've already labeled.

---

## Why this exists

The theme axis is **asymmetric by design**: it BOOSTS a name when the theme is the driver, and never
penalizes a themeless name. That means its correctness has two independent failure sides, and a
labeled cohort has to cover both — a themed-only cohort is structurally blind to the second:

| stratum | rows | the failure it tests | the question you're answering |
|---|---|---|---|
| `themed` | 59 | **false positive** — we credited a theme that wasn't the driver | *Was the theme actually the driver of this move?* |
| `themeless_winner` | 131 | **false negative** — a real theme we never saw | *Was there actually a theme here that we missed?* |

The second stratum is your own point made mechanical: **not seeing a theme ≠ no theme exists** — which
is exactly why the EP should be able to feed back into theme discovery.

`themeless_winner` = themeless rows whose settled 5-day forward return cleared the established **+5%**
win bar. Themeless non-winners are deliberately not enrolled (review load); a control stratum is your
add if you want one.

## What to put in LABEL

Same three values for both strata — but the **question differs by stratum**, so check the `stratum`
column before you answer:

| value | on a `themed` row | on a `themeless_winner` row |
|---|---|---|
| `Y` | the theme drove it — peers moved too, it was a theme-wide bid | **yes, there WAS a theme we missed** — please name it in NOTE |
| `N` | idiosyncratic — a company-specific catalyst; the theme was incidental | genuinely idiosyncratic, no theme behind it |
| `?` | can't tell from what's here | can't tell from what's here |

`?` is a real answer, not a cop-out — it keeps a guess out of the ground truth. Leaving a row blank
is also fine; blanks are simply not counted.

**The NOTE column earns its keep on `themeless_winner` + `Y` rows.** Naming the theme we missed is the
single highest-value output in this whole exercise — those names are the direct input to closing the
discovery blind spot, and no amount of weight calibration substitutes for them.

## Columns you're given

`date · ticker · grade · theme · fwd_5d_pct · catalyst_type · catalyst`

`theme` is what the engine assigned (`-` on themeless rows). `catalyst` is the alert's recorded
catalyst text, truncated to 220 chars — usually enough to tell a company-specific event from a
sector-wide one. `fwd_5d_pct` is close-basis and present only where the outcome settled.

## What it unlocks

This cohort is **the gate on #335** — the theme-axis load-bearing flip. That flip's criterion is
grade-correctness measured over a themeless-winner-inclusive labeled cohort, full stop. No labels →
no correctness measurement → no calibrated weights → the flip cannot be evaluated, and everything
downstream of it stays parked.

Downstream of the flip is the set of uses you named: **boosting capital allocation toward hot areas
with EPs, arbitrating between competing EPs for limited slots, and expanding a slot for a given
theme.** None of those are reachable while the axis is dark, and all of them need a *calibrated*
weight rather than an implicit one.

It also feeds **#504** (the meta-rubric roadmap) — the labeled cohort is what turns "the judge weighs
theme somehow" into a measured, traceable weight.

## Honest limits — read before you start

1. **The cohort is May-heavy.** `themeless_winner` breaks down 13 April / 104 May / 14 June / **0
   July**. May supplied most of the winners; the current correction has produced none yet. Any weight
   fitted here is fitted mostly to May's regime, which is not today's. Worth knowing before the
   numbers get treated as settled.
2. **9 of the 59 themed rows have no catalyst on record** (March + early April — they predate alert
   coverage for that join). They read `(no catalyst on record)`. Label from memory if you have it,
   otherwise `?`.
3. **Most early themed rows have no settled forward outcome.** That's expected — themed rows enrol
   regardless of outcome, since the false-positive question doesn't depend on the return. It does mean
   those rows can't participate in the later outcome join.
4. **Forward returns select the themeless stratum; they are not evidence about the theme.** `fwd_5d`
   defines *which* themeless rows got enrolled ("winner"). Don't read a big number as support for a
   theme having existed — the attribution signals themselves stay as-of-alert-date.
5. **`fwd_5d_pct` is the stock's close-to-close move, not a trade outcome.** Same caveat that applies
   across the cooldown and missed-opportunity work.

## When you're done

Tell me and I'll ingest the sheet into `mi_theme_relevance_cohort` (already seeded with all 190 rows;
`operator_label` / `operator_note` / `labeled_at` are waiting). Partial is fine — I can ingest in
passes as you go, and the upsert is guarded so an ingested label is never clobbered by a re-seed.

---

*Cohort seeded from `mi_theme_axis_shadow` (476 rows → 190 enrolments) via
`scripts/seed_theme_relevance_cohort.py`, enrolment rule = the shared
`theme_axis_shadow.classify_label_stratum`. Enrolment numbers persisted per row
(`enrol_fwd_5d_pct` / `enrol_n_sessions_5d`) so the selection stays re-checkable.*
