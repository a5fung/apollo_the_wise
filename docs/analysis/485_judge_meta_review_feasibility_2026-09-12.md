# #485 — Should a meta-LLM review the judge? No: the yes-branch already runs, and the data cannot yet say whether the judge is miscalibrated

**Date:** 2026-09-12 (PT) · **Task:** #485 (LLM-advisor reviews the judge, operator idea 6/18) ·
**Cost:** $0 — read-only over code and prod rows, no model called · **Status:** feasibility read;
nothing built, nothing flipped.

---

## The answer

**Do not build it. Retire #485 as a distinct build.** Every mechanism the idea proposes is
already live at zero authority, and the one question it would add — *were the judge's calls
right?* — is already a registered data-gated review waiting on rows, not on a design:

- **A second, independent LLM already reads every one of the judge's HIGH decisions** on the
  identical evidence, same morning (#301, `judge_divergence.py`). Coverage since it went live:
  **97 of 97** distinct judge-HIGH alert-days (2026-07-27 → 09-08).
- **The forward-outcome question is already filed** as `judge_divergence_marginal_high_signal`
  in `data_gated_reviews.yaml`. It fires at 15 settled disagreements on the current model pair;
  it sits at **8 of 15** today.
- **The operator-labelling sampler already exists** — #337's monthly review ends by asking him
  to `/why` the demotes and top promotes and label each right/wrong. It was verified-live at
  close (7/1); the monthly sweep that carries it has run 4 times, most recently 2026-09-01
  (the review's own send sits inside a non-critical try/except, so the job status cannot
  confirm the message went out — see §What this does not answer).
- **A meta-LLM that "flags questionable calls" is a self-score** (ADR 0011: the agent never
  scores the judge) unless it is only a sampler for his labelling — and the sampler exists.
- **Under the rules that run today (rubric v4, 2026-08-28 on) the judge has decided 10 alerts,
  4 with a settled outcome.** No reviewer, human or model, can read calibration off that.

**One structural gap is real and small:** the second opinion is triggered on HIGH verdicts only,
so the judge's **17 demotions since 07-27 have had no same-day second read** (0 of 17). #337
already lists demotes-that-ran after the fact, so this is a same-day read vs an after-the-fact
list — both samplers for his labelling. That is a one-line trigger change to #301, not a new
reviewer, and it is **his call** (fork below).

---

## The decision this serves, and what would change it

- **Decision:** whether to spend design + shadow effort (and ~daily LLM calls) on a
  judge-reviewer, per the #485 DoD: *does a meta-LLM add signal over the operator-labelled sample
  + #337's by-tier cross-tab? yes → design + shadow; no → retire.*
- **Would have changed the answer to "yes":** (a) a class of judge decision that no existing
  surface reads at all; or (b) a settled cohort large enough, under one rule era, that a
  reviewer could point at a miscalibration the deterministic cross-tab cannot. Neither holds
  (§3, §4).
- **What would make this analysis wrong:** if the surfaces below were not actually running
  (checked — all three ran successfully this month), or if the divergence coverage were partial
  (checked — 97/97).

## Method

**Population:** `mi_ep_alerts` rows with `grade_engine_authority = 'judge'` (the judge drove the
tier), `alert_date >= 2026-06-10` (the day it went load-bearing) → **184 rows = 181 distinct
ticker-days** (3 duplicate rows: MANE 07-15, KMT 08-05, ACMR 08-07 — all three HIGH → HIGH,
so only that cell of §2c is row-inflated: 109 rows = 106 distinct; every count in §2d was
recomputed on distinct ticker-days). `mi_judge_divergence`, all 97 rows (07-27 → 09-08, no
duplicates). Outcomes joined from `mi_ep_scan_outcomes` on `(ticker, scan_date = alert_date)`.
Read 2026-09-12 from prod, read-only.

**Outcome column:** `fwd_5d_pct` is `(max high over 5 sessions − baseline close) / baseline
close` — a **maximum favourable excursion (MFE)**, not a return. Every "5d" figure below is MFE.
Tail counts (≥20%, ≥40%) and p90 are shown before the median, per the analysis standard.

**Rule eras inside the window** (why nothing here is a calibration claim):

| date | what changed | source |
|---|---|---|
| 2026-07-31 | JUDGE_MODEL opus-4-8 → opus-5; divergence model sonnet-4-6 → sonnet-5 | `mi_model_resolution` |
| through 2026-08-07 | judge responses cut at 500 tokens; verdicts graded on truncated JSON (5 of the 33 current-pair divergence rows 08-04→08-07 carry a NULL primary confidence = the truncation signature) | ADR 0011 addendum 08-07 |
| 2026-08-22 | score separation + shortlist changed what reaches the judge | `rule_eras.py` |
| 2026-08-27 | rubric v3 → v4 (axis split; second-opinion block shown to the judge) | `ep_grade_judge.RUBRIC_VERSION` |

## 1. What exists today, and what it already catches

| surface | what it reads | what it flags | cadence · last run | who reads it |
|---|---|---|---|---|
| **#301 `judge_divergence.py`** | the judge's HIGH verdict + the identical payload, re-graded by a different-tier model (Sonnet) | tier disagreement; direction (stricter/looser); >25% weekly rate gets a ⚠ | every judge-HIGH, same morning · 09-08 | weekly system review, one line (19 runs, last 09-06) |
| **`judge_divergence_marginal_high_signal`** (gated review) | disagreed-HIGH vs agreed-HIGH forward MFE, current model pair only | whether the stricter second read identifies weaker HIGHs | fires at 15 settled disagreements · **8/15 now** | operator, when it fires |
| **#337 `judge_review.py`** (monthly) | every judge-driven alert × MFE, by judge direction and by tier set; demotes that then ran ≥+5%; second-opinion siding before/after rubric v4; realized P&L on traded ones | nothing — surfaces, then asks him to label demotes + top promotes via `/why` | monthly · carrier sweep 09-01 (4 runs; the send itself is not logged) | operator (Telegram) |
| **16:25 judge-delta digest** | the day's promotes/demotes with rationale | tier moves, same day | daily · 09-11 (69 runs) | operator (Telegram) |
| `ep_grade_decision` audit + `/why` | full decision trace per alert (rationale 184/184, judge's catalyst read 184/184, grounded text 174/184) | — | per alert | operator on demand |

Everything a meta-reviewer would read is already persisted, and every class of judge decision
except demotions already gets an independent model's read the same morning.

## 2. The numbers

### 2a. The second opinion, by model pair (`mi_judge_divergence`, n=97)

| model pair | window | n | disagreed | direction | disagreement rate |
|---|---|---|---|---|---|
| opus-4-8 / sonnet-4-6 | 07-27 → 07-31 | 18 | 9 | all 9 stricter (HIGH→MODERATE) | 50% |
| opus-5 / sonnet-4-6 | 08-03 | 2 | 0 | — | 0% |
| **opus-5 / sonnet-5 (current)** | 08-04 → 09-08 | **77** | **8** | all 8 stricter | **10%** |

The 50% rate that read as "the judge is a coin flip" was the old Sonnet's tier bias; on the
current pair the second model disagrees one time in ten, always in the stricter direction, and
the weekly ⚠ (>25%) has not fired since.

### 2b. Did the stricter second read identify weaker HIGHs? (current pair, MFE — a flag, not a finding)

| cohort | n | settled | ≥20% | p90 | mean | median |
|---|---|---|---|---|---|---|
| second model **disagreed** (HIGH→MODERATE) | 8 | 8 | 1 | 20.7 | 11.8 | 8.1 |
| second model **agreed** HIGH | 69 | 64 | 4 | 17.0 | 9.0 | 7.9 |

At n=8 this says nothing — and what it hints at is the wrong direction for the idea: the names
the stricter model would have demoted ran at least as far (KURA +27.9, RDW +17.6, KTOS +16.1).
The registered review will make this read at 15; at the last three weeks' volume (about 4
judge-HIGHs a week, 10% disagreement) that is roughly **four more months**.

### 2c. The judge's decisions by era — this is a sizing table, not a calibration

| our score → judge tier | rows (all eras, 06-10 → 09-08) | settled | ≥20% | ≥40% | p90 | median | rows under **current rules** (v4) | settled |
|---|---|---|---|---|---|---|---|---|
| HIGH → HIGH | 109 | 104 | 10 | 2 | 19.9 | 7.2 | 8 | 3 |
| HIGH → MODERATE | 17 | 16 | 1 | 1 | 13.5 | 5.7 | 2 | 1 |
| HIGH → none | 2 | 2 | 0 | 0 | 3.8 | 3.5 | 0 | 0 |
| MODERATE → HIGH | 28 | 28 | 5 | 2 | 28.1 | 13.0 | 0 | 0 |
| MODERATE → MODERATE | 19 | 19 | 0 | 0 | 15.9 | 5.2 | 0 | 0 |
| MODERATE → none | 9 | 9 | 2 | 0 | 20.9 | 7.3 | 0 | 0 |
| **total** | **184** (181 distinct) | 178 | 18 | 5 | | | **10** | **4** |

The all-eras column spans two judge models, a truncation defect, an admission change and a
rubric change. It sizes the corpus; it cannot grade the judge. The corpus a reviewer could
honestly grade — current rules — is **10 decisions, 4 settled, and not one promotion or
suppression among them.** Judge-driven alerts ran 6 · 3 · 6 in the last three weeks, so this
grows by roughly 20 a month.

### 2d. Coverage of the existing second opinion (distinct ticker-days since 07-27)

| judge decision class | n | with a second-opinion row |
|---|---|---|
| judge set HIGH | 97 | **97** |
| promoted MODERATE → HIGH (subset of the above) | 18 | 18 |
| **demoted** (HIGH → MODERATE/none, MODERATE → none) | 17 | **0** |

### 2e. Two case-level checks (both flags; n stated)

- **The only known-defective judge calls we have** are the two HIGH promotions ADR 0011's 08-07
  addendum identifies as decided by a truncated response (AMRC 08-04, RDW 08-06). The second
  opinion disagreed on RDW and agreed on AMRC — **1 of 2 caught.** That is the entire test set
  for "does a second read catch a bad call".
- **The operator's own EP list** (`docs/methodology/operator_labelled_eps.md`, 7 names): 4
  reached the judge (PLTR, TEAM, HTFL, MRNA) and on all 4 our score, the judge and the second
  model all said HIGH — nothing for any reviewer to flag. The 3 misses (BFLY, ABNB, CHPT) have
  **no alert row at all**: they failed at admission or the floor grader, upstream of anything a
  judge-reviewer reads.

### 2f. Real money rides on these calls (why calibration matters — and why P&L is not the way to read it)

93 distinct judge-HIGH-held and 23 judge-promoted alert-days became **live** trades since 06-10.
Their realized P&L pools four exit eras (A/B/C/D, `rule_eras.py`) and is not quoted here; a
meta-reviewer reading "outcomes" would be reading exactly that pooled number, or MFE.

## 3. Why a meta-LLM adds no signal over what runs

1. **Mechanism is duplicated.** "A second LLM reads the judge's decision and disagrees" is
   #301, live on 97/97 HIGHs. Reading the decision *plus the outcome* adds only the outcome —
   and the outcome available is MFE (not a return) or era-pooled P&L (§2f). A model reading
   those would be pattern-matching on the same contaminated column the deterministic join
   already tabulates, at a per-call cost, with less transparency.
2. **Flagging is scoring.** A reviewer that marks a call "questionable" has scored the judge.
   ADR 0011 reserves that verdict for the operator; the CLF/WKC precedent (both demotes ran
   +5% in 5d, he ruled both correct — *"not true EP moving"*) shows a price-based flag is
   often simply wrong about what an EP is. The only permitted role is a sampler for his labels,
   and #337 is that sampler.
3. **The corpus under current rules cannot support the claim** (10 decisions, 4 settled).
   Anything a reviewer said today would be about rubric v3, opus-4-8 verdicts, or truncated
   JSON — a system that no longer exists.
4. **The wait already exists.** The outcome question is registered at 8/15 on the current pair.
   Filing #485 as "can't tell yet" would create a second wait for the same question.

**Two observations worth surfacing, not fixing here:**
- `judge_divergence_marginal_high_signal` is era-scoped on the model pair but **not on rubric
  version** — it will pool v3 and v4 disagreements, the same mixing it was written to avoid
  for models. Worth a one-line predicate change when the review is next touched.
- The 17 `judge_divergence_detected` audit rows (07-27 → 08-27) are Telegram-free by design;
  the weekly line is the only operator-facing surface for #301, and it renders only the rate
  and direction, never the names.

## 4. The fork (operator's call)

| option | what it is | cost |
|---|---|---|
| **(a) retire #485** | the yes-branch is built; the outcome question lives in the #301 gated review | none |
| (b) retire #485 **and** widen #301's trigger to demotions | the 17-and-counting demotes get the same same-day second read HIGHs get; zero authority, logs only | ~1–2 extra Sonnet calls/day; a trigger edit in `ep_detector._judge_shadow` |

**Recommendation: (a).** #337 already lists demotes-that-ran for his labelling; a same-day
second read on demotes adds a row he does not currently ask for. If he wants the demote side
covered, (b) is a scope change to a shadow, not a new system.

⚖ **THE LINE:** nothing was changed, flipped or scheduled. The second opinion keeps zero
authority. Widening its trigger, retiring the task, or ever letting any reviewer's output touch
a grade are the operator's decisions.

## What this does not answer

- **Whether any of the judge's 181 decisions was right or wrong.** No number here is a verdict
  on a call; MFE is not an EP, and the operator is the only scorer (ADR 0011).
- **Whether the judge is miscalibrated under current rules.** 10 decisions / 4 settled since
  rubric v4 — unreadable; §2c's all-eras table cannot be used for this.
- **Whether Sonnet is the right second tier**, or whether a third model would disagree
  differently. The 50% → 10% shift on the model swap shows the disagreement rate is a property
  of the pair, not of the judge.
- **Whether a same-day second read on demotes would change his labelling rate** — the demote
  side has n=0 second reads, so option (b) is unmeasured, not measured-and-rejected.
- **Anything about the 3 labelled EPs that never reached the judge** — those are admission /
  floor-grader questions (#210, #624, the low-cap lane), outside this task.
- **The realized-R quality of judge-driven trades** — pooled across four exit eras; needs the
  #482 era-stamped recorder, not this join.
- **Whether the 09-01 monthly judge review actually reached Telegram.** `mi_job_runs` records
  the carrier sweep as `success`, but `quarterly_review.py` wraps the review's send in a
  non-critical try/except, nothing persists outgoing messages, and the container was rebuilt
  on 09-12 so the 09-01 log is gone. The sampler is verified-live from 7/1; its 09-01 delivery
  is inferred, not observed.

## Appendix — the reads (all `SELECT`, run once 2026-09-12, captured to file)

- Divergence by pair / split by `agree` × MFE: `mi_judge_divergence d LEFT JOIN
  mi_ep_scan_outcomes o ON (o.ticker, o.scan_date) = (d.ticker, d.alert_date)`, grouped by
  `(primary_model, secondary_model, agree)`.
- Gated-review predicate: verbatim from `data_gated_reviews.yaml` → 8.
- Era matrix: `mi_ep_alerts a LEFT JOIN mi_ep_scan_outcomes o`, `grade_engine_authority='judge'`,
  grouped by `(baseline_floor_tier, judge_tier)`; current-rules column adds
  `rubric_version LIKE 'v4%'`.
- Coverage: distinct `(ticker, alert_date)` judge-HIGH / demote / promote since 07-27, LEFT JOIN
  `mi_judge_divergence`.
- Surfaces running: `mi_job_runs` — `weekly_system_review` 19 × success (last 09-06),
  `monthly_backward_check_sweep` 4 × success (last 09-01), `judge_delta_digest` 69 × success
  (last 09-11).
- Duplicates: `GROUP BY ticker, alert_date HAVING COUNT(*) > 1` on both tables.
