# #212 dialogic-loop prototype — first empirical result (2026-06-07)

**Script:** `scripts/proto_dialogic_dossier.py` (READ-ONLY; no DB write, no scheduler).
Rung 1.5 of ADR 0006: tool-grounded INVESTIGATOR (Sonnet) → skeptical-PM ADVISOR
(Opus, no tools) → INVESTIGATOR revise. Mechanical anti-confabulation check
(verbatim-quote substring) on every claim. Run on prod, all-history unknown/
coverage-gap EP cohort.

## The one question it tests
Does an independent skeptical-PM advisor-pass over a grounded investigator's catalyst
dossier **add value the investigator (and the mechanical check) cannot** — catch
confabulations, flip wrong verdicts? Or is it ceremony? (operator #212 thesis: "make
the thing that caught my errors today, autonomous"; the production version of `advisor()`.)

## Result — N=2 (the unknown/coverage-gap cohort is now small; sourcing improved)

The headline is NOT "it produced the correct verdict." Across **three identical runs** of
ABVX the PM returned **different verdict labels** (`no_real_catalyst` once, `unconfirmed`
twice; the investigator said `catalyst_confirmed` every time). The verdict *label* is
**run-unstable**, and `no_real_catalyst` is arguably *wrong* — a Phase-3 readout that
moved the stock ~44% IS a real catalyst, just bearish. So credit the **critique, not the
verdict.**

| name | what's ROBUST across runs | verdict label | mechanical check |
|---|---|---|---|
| **ABVX** 06-03 | PM **always** caught the same material omission (v1 cherry-picked favorable efficacy/safety, ignored the malignancy signals / ~44% gap-down) | **run-unstable** (`no_real_catalyst` ↔ `unconfirmed`); sometimes wrong | all 5 v1 claims PASSED — check blind to the omission |
| **RUM** 06-04 | PM kept the real $270M NVIDIA deal (no over-skeptic), pruned 1 unsupported interpretive claim | stable `catalyst_confirmed` | false-FAILED the real $270M quote (HTML-entity bug) |

**The defensible win: the omission-catch is stable and is value the mechanical grounding
check structurally cannot provide** (every ABVX claim passed the substring test, yet the
conclusion was wrong by selective reading). The verdict *layer* the PM then assigns is
not yet trustworthy. That is a sharper, more useful result than "correct flip": the
durable value is the **critique**; the **verdict label needs work before it drives anything.**

### Why ABVX is the load-bearing case
The investigator grounded **all 5** claims (every quote really in the 6-K) and still drew
the wrong conclusion: it cherry-picked the positive efficacy + "favorable safety, no new
safety signals" lines. Reality: ABVX **gapped DOWN ~44%** on disclosed **rare malignancy/
cancer signals** in the same Phase-3 trial. In **every** run the skeptical-PM caught the
selective reading — *"you cherry-picked the favorable safety line while ignoring [the
sources flagging] the ~44% gap-down on malignancy signals."* The mechanical check could
NOT catch this (all claims passed); it took the advisor's *judgment*. That is exactly the
value rung-1 self-critique would miss and the rung-1.5 independent pass provides —
empirical support for the ADR 0006 ladder choice. (The verdict-label instability is the
work that remains, not a refutation of the pass.)

### Schema finding (for the production build)
`unconfirmed` is itself a poor label here — the catalyst WAS confirmed, it was just
**bearish**. The taxonomy `{catalyst_confirmed, unconfirmed, no_real_catalyst}` has no
slot for "confirmed, net-negative direction," forcing an incoherent label on a
directional miss. The eventual `mi_catalyst_dossiers` output needs a **direction/sign
field separate from catalyst-presence** (presence ≠ bullish).

### RUM — the pass did not over-skeptic a real fire
Kept `catalyst_confirmed` for the genuine $270M NVIDIA Blackwell B300 GPU-cloud deal
(real 8-K), and pruned one unsupported interpretive claim ("gap-up reflects investor
optimism..."). No false flip — the skeptical prior did not destroy a real catalyst.

## Two real bugs the run surfaced (fix before any promotion)
1. **HTML-entity false-negatives in the mechanical check.** SEC text carries `&#8220;`
   / `&#8710;` / `&#8221;` entities; RUM's real $270M quote *false-failed* the substring
   check on an entity/whitespace mismatch. → decode HTML entities (and the typographic
   quotes) before `_quote_grounded`'s normalize. Currently inflates the "ungrounded" count.
2. **Revise-step JSON truncation/malformation.** The investigator's revise occasionally
   returns malformed/truncated JSON (`Unterminated string` / `Expecting property name`),
   silently falling back to v1 and **destroying the very signal measured** (did v2 honor
   the PM?). → robust parse + higher max_tokens + a one-shot reformat-retry.

## Honest verdict & next step
- **POC-positive but N=2.** Directional proof the advisor-pass adds judgment the
  mechanical check and a lone investigator lack. NOT a graduation — the cohort is too
  thin to size the value or the false-flip rate.
- **Next (gated, not now):** (a) fix the 2 bugs **+ add a direction/sign field** to the
  dossier schema (presence ≠ bullish — the ABVX label incoherence); (b) widen the cohort
  (longer lookback / include graded strong+gc generally, not only the shrunken unknown
  set) to N≥10–15 and measure, against eyeballed source truth, **both (i) verdict
  STABILITY** — re-run identical inputs k times; the ABVX run-instability
  (`no_real_catalyst` ↔ `unconfirmed` across 3 runs) means the label layer is not yet
  reliable enough to drive anything — **and (ii) false-flip rate** (did it kill a real
  catalyst), not merely "did it flip"; (c) only then consider promoting to the nightly
  `mi_catalyst_dossiers` job per ADR 0006 §3.
  **Promotion is operator-gated** — this is advisory discovery, and the HARD-gate rule
  (agent must not declare a discovery loop "production-ready" without operator judgment)
  applies. Two ungrounded LLMs can converge on a confident hallucination; the grounding
  enforcement + bounded asymmetric pass is what guards it, and that guard needs a real-N
  false-flip measurement before it carries weight.

## Post-fix update (2026-06-07, same session) — 3 bugs fixed + the schema gap closed

Applied + verified on prod (N=2 re-run):
1. **HTML-entity/typography normalization** in the grounding check (`html.unescape` +
   curly-quote/dash fold) → RUM's real $270M quote no longer false-fails; both names now
   `ungrounded=0`.
2. **Revise-JSON robustness** (`_llm_json` one-shot reformat-retry) → the silent
   `Unterminated string` → v1-fallback is gone; v1→critique→v2 completes cleanly.
3. **Direction/sign field** (`bullish | bearish | neutral`, separate from `verdict`) →
   **closes the ABVX incoherence.** Post-fix, ABVX reads coherently: v1 `confirmed+bullish`
   → PM `confirmed+**bearish**` (keeps the real catalyst, flips the SIGN on the malignancy/
   gap-down) → v2 honors it. The PM's value now surfaces as a **stable, coherent direction
   flip**, not the earlier thrash between `unconfirmed`/`no_real_catalyst`. RUM stays
   `confirmed+bullish` (no over-skeptic).

This is a sharper, more coherent picture than the pre-fix run — but it is **still one run,
N=2.** Do NOT read "the direction flip is correct and stable" as established: the gated
eval (verdict+direction **stability** across repeated identical runs, + **false-flip rate**
vs eyeballed truth, on **N≥10–15**) is still the bar before promotion. What IS now true:
the two mechanical bugs are closed and the schema can represent "confirmed-but-bearish,"
so the widen-cohort eval can measure the right thing.

### Spend cap + measured cost (the eval is bounded)
The harness now has a **hard, mechanical spend cap** (`--max-spend`, default $2): it tracks
ACTUAL token usage from each API response and **refuses to start a call** once the budget
is reached (proven: a $0.05 cap stopped after 1 name at $0.096, bounded overshoot ≈ one
name's calls). `--repeats k` re-runs each name k× and the summary reports per-name verdict+
direction **stability** (the gated metric). **Measured per-name cost = $0.096** (3 calls:
Sonnet v1 + Opus critique + Sonnet v2). So the N≥10–15 × k=3 eval is ≈ $3.50, capped safe.

### Model note — Opus is prototype-only
Production Apollo uses **no Opus**; the critic role here runs on Opus (`ADVISOR_MODEL`),
the investigator on Sonnet. ADR 0006 originally spec'd the advisor as *Sonnet* — so the
widen-cohort eval should also test **Sonnet-as-critic vs Opus-as-critic**: if Sonnet
catches the same omissions (e.g. the ABVX cherry-pick), the loop graduates with **no new
model in production**. Promoting #212 with an Opus critic = the first Opus in a prod path
(a small new cost center, ~pennies/day) and is an explicit operator decision.

## Widened-cohort eval (2026-06-07) — N=10 × k=3, Opus vs Sonnet critic

Ran the gated eval (cohort=both: recent strong/gc + the unknown-gap names), 3 repeats per
name, both critic arms, hard spend cap. **Headline: the loop is STABLE and catches genuine
confabs — but its `no_real_catalyst` flips include real, sourcing-driven FALSE NEGATIVES,
so it is NOT a grading gate; it is a sourcing-QA detector downstream of #210.**

| | Opus critic | Sonnet critic |
|---|---|---|
| Stability (distinct v2 label across 3 repeats) | **10/10 stable** | 8/10 — PGY + LAC thrash (no_real ↔ unconfirmed) |
| Confabs caught | 35 | 17 |
| Verdict flips (→ skeptical) | PGY, NVTS, GRRR, LAC | PGY, NVTS, GRRR, LAC |
| Spend (N=10×3) | $3.11 | $1.22 |

### The load-bearing finding — GRRR: a sourcing-driven FALSE FLIP (operator catch)
GRRR gapped **+17.6%** on 2026-06-02 on a real **$2B Supermicro India AI-infrastructure
deal**. But the pipeline's stored catalyst captured only "AI/speculation... **rather than
an acquisition or large contract**" (it *affirmatively ruled out* the $2B contract) + a
net-loss Q1 — the deal was **never in the evidence pack** (sources = stored_catalyst +
stored_analysis only; no SEC filing; the PR was not ingested). Given that incomplete pack,
**both** the investigator AND **both** critic models reasoned correctly-on-evidence to a
**confident `no_real_catalyst`** — a false negative on a real $2B-deal EP.

⇒ **A grounded dialogic loop AMPLIFIES sourcing gaps into confident wrong "no catalyst"
calls.** Garbage in → *confident* garbage out. The false-flip is **model-independent**
(Opus and Sonnet both commit it), so it is a **sourcing** problem (#210), not a critic
problem. The loop's skepticism is only correct when sourcing is complete.

### Flip adjudication (eyeballed vs the stored catalyst)
- **PGY** → `no_real_catalyst`: ✅ correct (pipeline itself says "short-squeeze, no
  fundamental"; matches the known PGY fake-earnings confab, memory
  `feedback_catalyst_sourcing_direct_over_llm`).
- **GRRR** → `no_real_catalyst`: ❌ **false-flip** (real $2B deal missing from sources).
- **NVTS / LAC** → skeptical: ⚠️ gray (pipeline itself hedged "rather than a single
  headline"); Opus says `no_real_catalyst`, Sonnet the softer `unconfirmed`.

False-flip rate ≥ 1/10, sourcing-origin — exactly the metric the eval existed to surface.

### Verdict + the reframe (stated at the precision the data supports)
- **The clean, sourcing-INDEPENDENT value-add is ABVX** (not the flip count). Complete
  evidence pack (6-K present), investigator cherry-picked the bullish efficacy lines, PM
  correctly flipped *direction* to bearish on the malignancy/gap-down — value the mechanical
  grounding check provably cannot give, with **no sourcing confound**. That is the strongest
  evidence the advisor-pass earns its place. (The verdict-flip tally — 1 correct PGY / 1
  false GRRR / 2 gray — does NOT by itself carry "adds value.")
- **NOT a grading/suppression gate** until #210 sourcing is solid — downstream of
  incomplete sources the loop is a winner-suppressor (it would have killed the GRRR EP).
- **As a sourcing-QA feed it is LOW-PRECISION, not a high-confidence flag.** PGY and GRRR
  produce **identical** loop output (`no_real_catalyst`), yet PGY is a *true* no-catalyst
  (genuine squeeze) and GRRR is *false* (missed $2B deal). The loop **cannot distinguish
  "no catalyst because there is none" from "no catalyst because we missed it"** — that is
  the problem restated, not solved. So it is a **low-precision triage feed into #211**
  (good recall — it caught the one real gap; poor precision — it also fires on real
  squeezes), tolerable ONLY because #211's downstream re-source step is cheap (a false
  positive costs one wasted re-source). Do NOT anchor #211 on it as a reliable flag.
- **A/B:** Opus is **more stable** (10/10 vs Sonnet 8/10 — Sonnet thrashes on ambiguous
  PGY/LAC). But Opus is also **more aggressive** (2× confab-flags, harder `no_real_catalyst`
  calls), and on a substrate whose failure mode is *over-aggressive false-negatives* (GRRR)
  that is double-edged — Sonnet's softer `unconfirmed` on NVTS is arguably the more honest
  call. So: Opus wins on stability; Sonnet is less trigger-happy, which may matter more once
  you've seen the GRRR false-flip. Cost gap is pennies/day in a nightly job. Critic choice
  is a post-#210 decision; neither is promotable to a gate now.
- Stability (10/10 Opus), the direction field, and the ABVX-class genuine catches all hold.

## Side finding (data quality)
ABVX's `mi_ep_alerts.gap_pct` recorded **+15.1%**, but the catalyst reality was a ~44%
gap-DOWN. Either the stored gap is a stale/early reading or the name reversed hard
intraday. Worth a separate look (could be an EP gap-field accuracy issue). Filed as a
follow-up, not chased here.
