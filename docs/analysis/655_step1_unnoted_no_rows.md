# The 22 unlabelled NO rows — #655 step 1's unblocking sitting

**Built 2026-09-20 so tomorrow's sitting is ~10 minutes and the list is not re-derived.**

Each row needs ONE mark:

- **W** — the theme was WRONG for this stock
- **I** — the theme was fine; this stock moved for its OWN reason (earnings, FDA, an upgrade)

**Why it matters:** the labelling sheet defines a NO as *"idiosyncratic — a company-specific
catalyst; the theme was incidental"*, so today a NO cannot distinguish those two. 22 of 32 NOs
carry no note, four themes carry BOTH a yes and a no on different alerts, and until these are
split **no correctness bar can be signed** — which is what parks step 3 (#368's boost magnitude,
the Nascent exclusion that gave PLTR and MRNA no boost, the #335 flip).

Evidence: `docs/analysis/655_theme_sequence_evidence_2026-09-20.md`.
⚖ The bar itself is a detection threshold and stays his; this sitting only makes it settable.

## Method and population

**Population, derived by query not by hand:** every row in `mi_theme_relevance_cohort` where
`stratum='themed'` AND `operator_label='n'` AND `operator_note` is null or empty — **22 of the 32
NO rows (n=22)**, out of **103 themed rows labelled in total, n=103 (70 y / 32 n / 1 unsure)**, covering alerts
**2026-08-04 → 2026-09-08**. The catalyst shown against each is the latest `mi_ep_alerts` row for
that (ticker, alert_date).

⚠ **Two of my own errors on the way to this list, both caught by an empty result rather than by
me:** the cohort table has **no `theme_name` column** (the credited theme is joined from
`mi_theme_axis_shadow`), and its labels are **`y`/`n`, not `yes`/`no`** — the first filter returned
nothing at all.


| # | ticker | alert date | W / I | catalyst on record |
|---|---|---|---|---|
| 1 | **INSP** | 2026-08-04 |  | INSP reported Q2 2026 revenue of $200.6 million, which represents a 7.6% year-over-year DECLINE, driven by a drop in U.S. revenue amid an evolving cod |
| 2 | **LIFE** | 2026-08-04 |  | Ethos Technologies reported Q2 2026 earnings with revenue of $189.6M, representing 113% year-over-year growth — the second consecutive quarter of 100% |
| 3 | **APPS** | 2026-08-05 |  | Digital Turbine reported fiscal Q1 2027 earnings with revenue of $166.0M (+27% YoY), Non-GAAP Adjusted EBITDA of $42.5M (+69% YoY), and Non-GAAP EPS o |
| 4 | **AEVA** | 2026-08-06 |  | Aeva reported Q2 2026 earnings (8-K Item 2.02, filed Aug 5, 2026) alongside a highly compelling set of business developments: (1) a brand-new Optical |
| 5 | **QNST** | 2026-08-07 |  | QuinStreet's Q4 FY2026 8-K shows a massive beat with acceleration: record quarterly revenue of $373.9M up 43% YoY, GAAP net income up 496% YoY to $19. |
| 6 | **ACMR** | 2026-08-07 |  | ACMR reported Q2 2026 results with revenue up 36% YoY to $292.9M (vs $215.4M), driven by ECP (+168%) and advanced packaging (+153%) segments, alongsid |
| 7 | **TH** | 2026-08-10 |  | TH reported Q2 2026 results with revenue up 39% YoY to $85.5M and Adjusted EBITDA up more than 5x YoY to $18.2M, and importantly raised FY2026 revenue |
| 8 | **BW** | 2026-08-11 |  | BW reported Q2 2026 results beating consensus on all key metrics: revenue of $319.7M (+130% YoY, ahead of street), net income of $14.3M vs a loss of $ |
| 9 | **SE** | 2026-08-11 |  | Today's fresh catalyst is Sea Limited's Q2 2026 earnings release: EPS of $0.70 missed the $0.75 estimate, but revenue of $7.788B beat the $7.063B esti |
| 10 | **HRB** | 2026-08-12 |  | HRB reported fiscal 2026 (FY ended June 30, 2026) results with revenue up 4.9% to $3.95B, net income from continuing operations up 20.8% to $736.3M, a |
| 11 | **STDN** | 2026-08-14 |  | STDN's gap-up is driven by a cluster of fresh, bullish analyst initiations on 2026-08-10: William Blair (Outperform), RBC Capital (Outperform, $11 PT) |
| 12 | **LPTH** | 2026-08-14 |  | Fresh, dated catalyst: Piper Sandler initiated coverage on LPTH on 2026-08-12 with an Overweight rating and $15 price target, a significant premium to |
| 13 | **VERA** | 2026-08-14 |  | FDA granted accelerated approval of TRUTAKNA (atacicept) for adult IgA nephropathy patients at risk of progression, with alignment on an earlier ORIGI |
| 14 | **AMLX** | 2026-08-18 |  | Amylyx announced today (8/18/26) that its Phase 3 LUCIDITY trial of avexitide met its primary endpoint, with a 55% reduction in Level 2/3 hypoglycemic |
| 15 | **RARE** | 2026-08-20 |  | Fresh, company-specific binary catalyst: on 8/19/2026 Ultragenyx announced FDA accelerated approval of GENGLYCOS (DTX401), its first gene therapy, for |
| 16 | **UUUU** | 2026-08-21 |  | Concrete, fresh operational catalyst: Energy Fuels announced its terbium oxide from White Mesa Mill passed all qualifications for commercial use by on |
| 17 | **VEEV** | 2026-08-27 |  | VEEV gapped up on a clean Q2 FY2027 beat-and-raise: revenue ~$928M and EPS $2.35 topped estimates, with management raising full-year FY2027 guidance, |
| 18 | **AGX** | 2026-09-03 |  | Argan reported record Q2 FY2027 results (8-K filed 9/2/26): revenue of $384M, up 61.6% YoY from $237.7M, net income of $53.3M (up from $35.3M), dilute |
| 19 | **HOOD** | 2026-09-03 |  | Cluster of bullish analyst actions dated today (Morgan Stanley upgrade to Overweight with PT raised to $150 from $124, Piper Sandler PT raised to $145 |
| 20 | **ALAB** | 2026-09-04 |  | ALAB’s latest gap-up appears tied primarily to investor positioning ahead of its appearance at Citi’s 2026 Global TMT Conference on September 4, combi |
| 21 | **PHVS** | 2026-09-08 |  | Fresh, dated (9/8/2026 6-K) release of positive topline Phase 3 CHAPTER-3 pivotal data for deucrictibant XR in HAE prophylaxis: primary endpoint met w |
| 22 | **ROIV** | 2026-09-08 |  | Roivant's Pulmovant subsidiary announced positive Phase 2 PHocus topline data for mosliciguat in PH-ILD, meeting the primary endpoint with a statistic |

**22 rows.** Expected shape from reading the catalysts: mostly earnings beats and FDA/Phase-3
releases, which is the **I** pattern. If they land that way the live-path rate moves from **77%**
**(55 of 71, n=71)** toward the high 80s and a 90% bar becomes a real conversation — but that is a
PREDICTION, not a result, and the point of the sitting is that he decides each one.

## What this does not answer

- **It does not tell you whether any theme is right.** It sorts 22 NOs into two buckets so a bar
  becomes settable; the bar itself is his, and nothing here proposes a value.
- **It covers 22 of 103 themed rows (21%, n=103).** The other 67 unnoted YES rows are not re-examined —
  a YES is not ambiguous in the way a NO is, but that is an assumption, not a measurement.
- **It says nothing about themes we MISSED.** Recall rests on 31 labelled themeless winners from an
  8-day window in the May regime; 136 since are unlabelled by design.
- **It cannot pre-empt his answers.** The "expected shape" above is my read of the catalyst text,
  and the live-path figure it implies (**55 of 71 = 77%**, n=71, today) moves only once he marks the rows.
