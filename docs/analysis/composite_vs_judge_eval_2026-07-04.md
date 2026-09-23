# #335 flip evidence — does the #329 mechanical composite agree with / beat the holistic judge?

Read-only, zero-LLM eval. Every number below comes from stored data + a deterministic
recompute; no fresh extraction, no API call. Repo state: local HEAD as of 2026-07-04 AM;
**prod is at `80b4604` (2026-07-03 12:32 PDT)** — i.e. prod predates ALL of today's commits
(the #328/#330 ADRs, the #347 corpus flip). That version boundary is what makes "before the
flip" a clean, unambiguous cutoff here: the entire cohort below was scanned/graded by
pre-7/4 code.

## TL;DR

- **N = 22** EP alerts have BOTH a judge verdict and a recomputable 6-axis catalyst-rubric
  composite. Of those, the composite and the judge **agree only 8/22 (36%)**; **14/22 (64%)
  disagree**, and **100% of disagreements run one direction** — the composite would downgrade
  a name the judge fired/kept at HIGH. Zero cases of the reverse (composite says
  strong/game_changer, judge says MODERATE/none).
- Forward outcomes on the disagreement set (composite says weak/routine, judge said HIGH,
  n=12): **11/12 positive at 5d (mean +5.1%), 12/12 positive at 10d (mean +6.8%)** — directionally
  favors the judge, i.e. flipping to composite-authority today would have suppressed mostly-winning
  alerts. But the "both agree non-HIGH" bucket (n=7) shows an *equally* positive mean
  (+5.6%/+8.4%) — this specific cohort (all earnings-day catalysts that already cleared the
  gap/EP filter) drifts positive on average regardless of grade nuance, so the forward-return
  read is **not discriminating** at this N. Treat directionally only.
- The **theme-axis component** of "theme #328 + catalyst-magnitude + catalyst_type" (#335's
  named composite) contributes **zero** to this cohort: applying `theme_axis_credit()`
  (AS-OF, zero-lookahead) to all 22 rows changes **0/22** labels (19 themeless, 3 themed but
  none clear the near-miss/tie-break bands). It also isn't live yet — see Gaps below.
- **None of #335's 4 named gates are met.** This document is useful evidence, but it is
  explicitly **not** the gate — #335 requires the batched, LLM-paid
  `eval_judge_enrich --regrade` run, which this task was scoped to avoid.

## Two different "rubrics" — disambiguated up front

The codebase has two objects both called "rubric," and #329/#335's prose sometimes elides
them. This eval is about the **first**:

1. **`catalyst_rubric.py` / `catalyst_rubric_runtime.py`** — the mechanical, deterministic
   6-axis fundamentals scorer (revenue/EPS/margin/beat/guidance/milestone → `composite_scaled`
   0-39 → label `weak`/`routine`/`strong`/`game_changer`). Shipped 2026-05-19, **already live**
   as a downgrade gate (`CATALYST_RUBRIC_GATE_ENABLED=true` default, threshold 22) inside the
   conviction-floor path. Has no `rubric_version` column of its own. **This is "catalyst-magnitude"
   in #335's composite.**
2. **`ep_grade_judge.py`'s `RUBRIC_VERSION`** (`"v3-2026-06-12-catalyst-freshness"`) — the
   holistic judge's own internal *prompt* rubric version, persisted to `mi_ep_alerts.rubric_version`.
   Not a numeric score at all; a text label for which judge-prompt iteration graded the alert.

`#329`'s own architecture decision (PLAN.md, operator 6/18) was explicitly **Path A**: enrich the
ONE judge with axis inputs (has_direct_source, theme_stage/score, structure, gap) — *"Path B's
separate logistic numeric composite stays the forward-gated registry cross-check (NOT a 2nd
authority)."* Object #1 above **is** that Path-B cross-check artifact. So strictly, the current
architecture never intended the mechanical composite to stand alone as "the" authority — #335's
phrase "the #329 advisory composite becomes authoritative" most naturally reads as the axis
*inputs* becoming load-bearing **through** the judge (via `axis_reads`), not this standalone
scorer superseding the judge outright. Flagging this scope ambiguity for the operator rather than
picking a reading myself.

## Method

**Script**: local, ad hoc (`recompute_composite.py`, scratchpad — not committed; trivial re-run,
see Reproduce below). No LLM calls anywhere in this pipeline; `build_rubric_inputs_hybrid`'s
yfinance augmentation is a plain historical-data fetch, not a model call.

1. **Cohort assembly** (prod, SELECT-only):
   - `mi_ep_alerts` rows with `judge_tier IS NOT NULL`: **390** (2026-03-30 → 2026-07-01).
   - Of those, join `mi_ep_catalyst_metrics` on `(ticker, alert_date)` (the earnings-extraction
     cache the rubric needs): **38** rows — most EP alerts are non-earnings catalysts (FDA,
     M&A, product, macro) that the 6-axis fundamentals rubric structurally can't score; this is
     a **scope mismatch**, not a data gap. `mi_ep_catalyst_metrics` has 96 rows total (retention
     180d), so 38/96 (40%) of all earnings extractions also have a judge verdict.
   - Of those 38, rows where `raw_json->'q_revenue_usd'->>'yoy_pct' IS NOT NULL` (the composite's
     hard precondition — Axis 1 needs a revenue YoY number): **22**. This is the eval cohort.
2. **Recompute the composite** — pulled each row's `mi_ep_catalyst_metrics.raw_json` (the exact
   `extracted` dict `score_ep_with_rubric()` expects) via SELECT, ran
   `catalyst_rubric_runtime.score_ep_with_rubric(ticker, extracted, alert_date)` locally against
   the **current repo HEAD**. Verified this function is byte-identical to what's deployed: the
   last functional change to `catalyst_rubric.py`/`catalyst_rubric_runtime.py`'s scorer predates
   prod's `80b4604` HEAD (only a 5/20 label rename since, already in prod). No version skew.
3. **Theme-axis overlay** — for each of the 22 `(ticker, alert_date)` pairs, ran the AS-OF
   (zero-lookahead) theme-heat SELECT that mirrors `db.get_theme_heat_asof` (`theme_date <=
   alert_date`, `stage != 'Retired'`) directly against `mi_themes`, then applied
   `catalyst_rubric_runtime.theme_axis_credit()` (pure function, ADR 0015) locally to see whether
   the theme boost would move any label.
4. **Judge + outcome pull** — `judge_tier`, `judge_direction`, `judge_materiality_tier`,
   `score_tier`, `grade_engine_authority`, `rubric_version`, `catalyst_quality` from
   `mi_ep_alerts`; `fwd_5d_pct`/`fwd_10d_pct` from `mi_ep_scan_outcomes` (LEFT JOIN on
   `ticker, scan_date=alert_date`).
5. Cross-tabbed composite label vs judge tier; sliced by `grade_engine_authority` (judge-shadow
   vs judge-load-bearing era) and by month; checked confounders (#320/#321, #347, extraction lag).

### Reproduce
```sql
-- cohort
SELECT a.ticker, a.alert_date, a.judge_tier, a.judge_direction, a.judge_materiality_tier,
       a.score_tier, a.grade_engine_authority, a.rubric_version, a.catalyst_quality
FROM mi_ep_alerts a
JOIN mi_ep_catalyst_metrics m ON m.ticker = a.ticker AND m.alert_date = a.alert_date
WHERE a.judge_tier IS NOT NULL
  AND (m.raw_json->'q_revenue_usd'->>'yoy_pct') IS NOT NULL
ORDER BY a.alert_date;
```
```python
# per-row recompute (zero LLM)
from agents.market_intelligence.catalyst_rubric_runtime import score_ep_with_rubric
result = score_ep_with_rubric(ticker, extracted, alert_date)  # extracted = raw_json from above
```

## Cohort (N=22)

| Ticker | Date | Composite | Label | Judge tier | Judge dir. | Authority | catalyst_quality | fwd5d | fwd10d |
|---|---|---|---|---|---|---|---|---|---|
| CPA | 05-14 | 13.5 | weak | MODERATE | hold | floor | strong | +1.4 | +7.4 |
| ONDS | 05-14 | 13.5 | weak | HIGH | hold | floor | game_changer | +8.1 | +22.9 |
| AAP | 05-21 | 13.8 | weak | HIGH | promote | floor | strong | +4.1 | +6.3 |
| PONY | 05-26 | 22.0 | strong | HIGH | hold | floor | strong | +20.8 | +20.8 |
| DY | 05-27 | 16.1 | routine | HIGH | hold | floor | game_changer | +4.3 | +4.3 |
| KSS | 05-28 | 10.0 | weak | none | hold | floor | routine | +3.3 | +13.3 |
| PHR | 05-28 | 12.0 | weak | HIGH | hold | floor | strong | +12.8 | +12.8 |
| UMAC | 05-28 | 12.3 | weak | none | demote | floor | routine | +16.1 | +16.1 |
| A | 05-28 | 17.0 | routine | HIGH | promote | floor | strong | +4.2 | +4.2 |
| DLTR | 05-28 | 16.0 | routine | HIGH | hold | floor | strong | +3.4 | +3.4 |
| NTAP | 05-29 | 18.0 | routine | HIGH | hold | floor | strong | +7.0 | +7.0 |
| CHA | 05-29 | 13.5 | weak | HIGH | hold | floor | strong | +5.0 | +5.0 |
| PD | 05-29 | 12.0 | weak | none | demote | floor | strong | +7.5 | +7.5 |
| EWTX | 06-01 | 0.0 | weak | none | hold | floor | mna | +0.3 | +0.3 |
| SAIC | 06-01 | 15.0 | routine | MODERATE | demote | floor | strong | +2.9 | +2.9 |
| GME | 06-03 | 10.8 | weak | HIGH | hold | floor | game_changer | +4.0 | +4.0 |
| CBRL | 06-10 | 11.0 | weak | none | demote | floor | routine | +7.4 | +11.2 |
| NAVN | 06-11 | 20.7 | routine | HIGH | hold | **judge** | game_changer | -2.3 | +1.2 |
| SWBI | 06-18 | 20.2 | routine | HIGH | hold | **judge** | strong | +8.8 | +8.8 |
| MU | 06-25 | 22.0 | strong | HIGH | hold | **judge** | game_changer | -1.2 | -1.2 |
| SNX | 06-25 | 18.4 | routine | HIGH | hold | **judge** | game_changer | +1.7 | +1.7 |
| AVAV | 06-30 | 22.9 | strong | HIGH | promote | **judge** | routine | n/a | n/a |

`Authority=judge` (bold) = the 5 rows where the judge actually drove `score_tier` (load-bearing
since the 6/10 toggle). The other 17 are judge-**shadow** verdicts that didn't drive the live
grade — comparing the composite to those is composite-vs-shadow-judge, not composite-vs-live-grade.

## Cross-tab

Binary framing (the only one both scales support): composite `{weak, routine}` = "not
HIGH-worthy" vs `{strong, game_changer}` = "HIGH-worthy"; judge `{none, MODERATE}` = "not HIGH"
vs `{HIGH}`.

```
                        judge=HIGH   judge=MODERATE   judge=none   row total
composite weak (n=11)        5             1               5          11
composite routine (n=8)      7             1               0           8
composite strong (n=3)       3             0               0           3
composite game_changer (n=0) —             —               —           0
```

- **Agree** (weak/routine + none/MODERATE, or strong/game_changer + HIGH): KSS, UMAC, PD, EWTX,
  CBRL (5, both "not-HIGH") + CPA, SAIC (2, composite-weak/routine vs judge-MODERATE — counted
  agree under the binary framing) + PONY, MU, AVAV (3, both "HIGH-worthy") = **8/22 = 36%**.
- **Disagree**: ONDS, AAP, DY, PHR, A, DLTR, NTAP, CHA, GME, NAVN, SWBI, SNX (12) — composite
  says weak/routine, judge fired/kept HIGH. **14/22 = 64%** (12 above + CPA/SAIC if counted
  strictly rather than under the lenient MODERATE-as-agree framing — reported both ways: the
  headline 64% uses the lenient framing; a stricter none-only "agree" reading would push
  disagreement to 16/22 = 73%).
- **Zero** cases of composite-strong/game_changer paired with judge-MODERATE/none — the
  disagreement is 100% one-directional (composite conservative, judge less so).

### Judge-load-bearing era only (N=5, the subset actually comparable to "would this flip change
today's live grade")

NAVN/SWBI/SNX = composite routine, judge HIGH (disagree, 3/5); MU/AVAV = composite strong, judge
HIGH (agree, 2/5). **2/5 (40%) agree** in the era that actually matters for #335. N is far too
small to be more than a data point.

## Theme-axis overlay (the other named #335 component)

AS-OF (zero-lookahead) theme membership for the 22 pairs: **19/22 themeless**; SWBI (Fading),
MU (Mainstream), AVAV (Nascent). Running ADR 0015's `theme_axis_credit()`:
- SWBI: Fading → 0 credit by design (never negative, not boosted either).
- MU: Mainstream, composite 22.0, boundary-to-game_changer = 30.0 — not within the 2% tie-break
  band → 0 credit.
- AVAV: Nascent, composite 22.9, boundary 30.0 — not within the 10% near-miss band → 0 credit.

**0/22 labels change.** The theme-axis component contributes nothing measurable in this cohort —
read as "not yet triggered at this N," not "the mechanism never matters" (the bands are narrow by
design). Separately, and more fundamentally: **this mechanism isn't live.** `theme_axis_credit()`
and its shadow writer (`log_theme_axis_adjusted_shadow` → `mi_audit_log` event
`theme_axis_shadow_adjusted`) were committed TODAY (`0d0303f`/`1bd2005`, 2026-07-04 07:34/AM
PDT) and are **not deployed** (prod HEAD `80b4604` predates them) — confirmed **0 rows** of
`theme_axis_shadow_adjusted` (and 0 of the failure-audit event) in prod `mi_audit_log` right now.
It also has no historical backfill — it only logs going forward from deploy. So "theme #328" as a
component of #335's composite currently has **zero accrued evidence of any kind**, live or
recomputed. (Separately, `mi_theme_axis_shadow` — a related but different STEP-0 telemetry table
from 6/24, 456 rows — records theme-heat/structural-attribution *alongside* grades for future
calibration; it does not compute a credit/adjusted label, so it isn't a substitute here.)

`catalyst_type` (the third named component) has no defined point value or weight anywhere in the
code — it's persisted advisory metadata (`catalyst_type`, `catalyst_type_rationale` columns), not
a scored composite input. There is nothing to mechanically fold into a composite for this axis at
all today.

**Net: the only #335 composite component with any accrued, recomputable evidence is
catalyst-magnitude (object #1 above). This whole eval is therefore a catalyst-magnitude-only
proxy for "the composite," not the full theme+magnitude+type object #335 describes.**

## Disagreement → forward-outcome tally

| Bucket | N | mean fwd5d | mean fwd10d | win-rate (>0) |
|---|---|---|---|---|
| Composite HIGH-worthy, judge HIGH (agree) | 3 | +9.8%* | +9.8%* | 2/2 settled |
| Composite weak/routine, judge HIGH (disagree — judge overrode) | 12 | +5.1% | +6.8% | 11/12 (5d), 12/12 (10d) |
| Composite weak/routine, judge MODERATE/none (agree) | 7 | +5.6% | +8.4% | 7/7 |

\*PONY +20.8/+20.8, MU -1.2/-1.2, AVAV n/a (too recent, no fwd window yet) — mean of the 2 settled.

**Read directionally only** (feedback: validate-metric-before-decision). The disagreement bucket
(n=12) and the "both agree non-HIGH" bucket (n=7) show **statistically indistinguishable** mean
forward returns at this N — this whole cohort is earnings-day catalysts that already cleared the
gap/EP filter, so positive 5-10d drift shows up almost everywhere regardless of grade nuance
(saturation, not signal). The only clean read: **zero disagreement cases where the composite's
implied suppression would have avoided a loser** — every single disagreement instance (12/12) had
a positive outcome at 10d. That is weak evidence against making the raw composite authoritative
on its own (it would have suppressed alerts that mostly worked), and it rhymes with this
codebase's own prior finding (6/5 backtest) that a naive single-axis gate over-suppresses winners
— but n=12 is nowhere near enough to hang a load-bearing decision on.

## Confounders checked

- **#320/#321 (live 6/28, `64e8ed4`)**: fixed stale-boost-reset + YoY-recovery on the floor path.
  21/22 cohort rows predate this fix (only AVAV, 6/30, is after) — the floor/judge inputs for the
  other 21 may carry the known pre-fix bugs. Does **not** affect the mechanical composite recompute
  (pure function of stored `raw_json`, untouched by #320/#321), only the judge/floor side of the
  comparison.
- **#347 corpus flip (LIVE `56bb422`, committed 2026-07-04 07:42 PDT)**: the entire cohort
  (max alert_date 06-30) predates this — clean, as instructed.
- **rubric_version / month drift**: 18/22 rows predate the judge's `v3-2026-06-12-catalyst-freshness`
  prompt (blank rubric_version); 4 postdate it (SWBI, MU, SNX, AVAV — all judge=HIGH,
  composite routine/routine/routine/strong). By month: 13 in 2026-05, 9 in 2026-06. No visible
  reversal in the disagreement direction across either split — the composite is conservative
  relative to the judge throughout, pre- and post-v3. N per slice (4-13) is too thin to call this
  a trend rather than noise.
- **Extraction backfill lag**: CPA/ONDS (both 05-14) were extracted 7 days after alert_date
  (`extracted_at` 05-21) — a post-hoc backfill, not a live-scan-time extraction. The other 20/22
  were same-day (same UTC morning as alert_date), i.e. genuinely live-scan-time extractions. This
  doesn't change the recompute's validity (still the identical deterministic function over stored
  data) but means 2 of the 22 rows couldn't have influenced their own live grade even in
  principle.
- **judge "grade" not persisted**: the judge's tool output includes a `grade` field
  (game_changer/strong/routine/mna — the same vocabulary as the rubric label) but only `judge_tier`
  (HIGH/MODERATE/none) is written to `mi_ep_alerts`. So a true label-vs-label (not label-vs-tier)
  comparison isn't reconstructable from stored data today — this is the single biggest "what's
  missing" gap in this eval, and the cheapest fix (a `judge_grade` column, populated going forward
  from the existing `_normalize_verdict` dict — no code/prompt change, no LLM cost) would make
  future eval passes materially cleaner.

## Against #335's own gate language

#335 (PLAN.md) names 4 non-negotiable gates for the flip: (1) CHANGE_PROCESS + operator sign-off
on exact weighting, (2) a DB toggle for instant revert, (3) the backtest = **one batched
`eval_judge_enrich --regrade` run** covering all pending axis enrichments at once, (4) [implicit]
evidence the flip is net-correct. Status:

| Gate | Status |
|---|---|
| CHANGE_PROCESS + sign-off on exact weighting | **Not started** — no weighting scheme for a standalone composite authority exists to sign off on |
| DB toggle for instant revert | **Not built** — `CATALYST_RUBRIC_GATE_ENABLED` is an env var (downgrade-gate only), not a composite-authority toggle |
| Batched `eval_judge_enrich --regrade` backtest | **Not run** — explicitly out of scope for this task (LLM spend); this doc is a zero-cost precursor, not a substitute |
| Net-correctness evidence | **Thin, N=22 (5 in the load-bearing era), directionally against** standalone composite-authority — see tallies above |

**This document does not satisfy the #335 backtest gate and isn't intended to.** It answers a
narrower, honest question: on the accrued data that exists today, the catalyst-magnitude
composite (i) disagrees with the judge far more than it agrees (64% vs 36%), (ii) disagrees in
one direction only (always more conservative), and (iii) on the thin forward-outcome evidence
available, that conservatism would have cost more winners than it screened losers. The theme-axis
and catalyst-type components of #335's named composite have no accrued evidence at all (theme:
built today, undeployed, zero rows; catalyst-type: no scoring mechanism exists). The operator's
decision — proceed to the batched paid regrade now vs. let the theme/structure/gap axes accrue
shadow data first — is exactly the fork #335 itself already names ("flip the core first" vs wait
for enrichment); this evidence leans toward **not** flipping the bare catalyst-magnitude composite
to standalone authority on its own, independent of when the batched regrade runs.
