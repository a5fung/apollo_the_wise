# ADR 0030 — Judge robustness: failure-mode taxonomy, adversarial corpus, and the grade-quality regression gate

**Status:** DESIGNED (Fable, 2026-07-11 eve — Block 3 T1 portion, run early to lighten Sunday).
Build cards are Opus/Sonnet work. **Nothing here changes live behavior**; the rubric amendment
loop (§6) is explicitly CHANGE_PROCESS + operator-sign-off gated. Serves the **7/18 M1 sitting
(#335)** — the judge gains authority with, for the first time, an adversarial robustness map.

**Problem.** `get_holistic_judge_enabled()` flips the judge load-bearing on 7/18, and nothing
adversarially tests it. The judge has ONE historical adversarial lesson encoded (the AKTS
stale-catalyst clause, rubric v3) — one clause per incident is whack-a-mole. We need (a) a named
taxonomy of the misdirection classes a grader must not fall for, (b) a corpus that tests all of
them plus the over-skepticism direction, (c) a repeatable eval, and (d) a **mechanical gate** so
no prompt edit / model swap / silent snapshot update ships ungraded ever again.

---

## 1. Failure-mode taxonomy (T1a) — 12 classes, each with the golden behavior

Grounded in the mined corpus (`docs/analysis/block3_t1_mined_corpus_2026-07-11.md`, 84 real
cases) + the rubric's own risk callouts. Classes 1–5 have live mined examples; 6–12 are
synthetic-only until one fires live.

| # | class | the misdirection | golden behavior |
|---|---|---|---|
| 1 | `mna_as_catalyst` | target/acquirer pop or broad rotation dressed as a company catalyst | grade `mna` / never HIGH-as-growth |
| 2 | `unconfirmable_underlying` | headline claim the corpus can't confirm (sparse, no q-rev) | ≤ MODERATE; say UNIDENTIFIED |
| 3 | `strong_print_no_heat` | real print, mature name, no theme/inflection (WDFC class) | demote from game_changer; strong at most |
| 4 | `stale_news_repackaged` | undated/old catalyst resurfacing as if new (AKTS class, rubric v3) | never HIGH on an undated driver |
| 5 | `structural_upgrade` *(positive)* | charter/approval that re-rates the company (CRCL class) | promote / HIGH retained |
| 6 | `dilutive_offering_as_growth` | ATM/offering/warrants framed as "strategic funding" | demote; financing ≠ catalyst |
| 7 | `promotional_microcap_pr` | buzzword pivot, unnamed-party LOI, no numbers | routine; never HIGH |
| 8 | `sympathy_no_own_catalyst` | peer's event lifts the name; no own event | routine; the driver belongs to the peer |
| 9 | `guidance_cut_inside_beat` | Q beat headline masks an FY guide-down | demote; the guide is the signal |
| 10 | `one_time_eps_anomaly` | loss→profit flip from asset sale / tax item (CBRL class, rubric §4) | not a turnaround; ≤ MODERATE |
| 11 | `immaterial_for_size` | small deal on a mega-cap, positively worded (rubric §2) | demote; materiality is relative |
| 12 | `transformative_for_size` *(positive)* | huge deal on a micro-cap the floor under-rated | promote; the mirror of #11 |

**Both failure directions are first-class.** Classes 5/12 + clean-print controls exist so the
gate catches an over-skeptical rubric drift (demote-everything) as loudly as a credulous one.
A judge that passes only by saying "routine" to everything must FAIL this eval.

## 2. Corpus (T1b) — two halves, one schema

- **Mined half (DONE, Opus 7/11):** `docs/analysis/block3_t1_mined_corpus_2026-07-11.json` —
  84 real cases (14 M&A / 14 unconfirmable / 14 boost-outcome-labeled incl. 9 FALSE_BOOST / 42
  live judge verdicts with rationales).
- **Synthetic half (THIS ADR, Fable-crafted):** `scripts/evals/judge_robustness_corpus_v1.json`
  — 28 adversarial + control cases covering classes 4, 6–12 (the classes with no/few live
  examples) + explicit positive controls. Every case is a **ready judge payload** in the exact
  `assemble_judge_inputs` shape (grounded_text, floor_tier, market_cap, has_direct_source, …),
  so the harness feeds them to `grade_holistic` with zero transformation.

**Scoring is predicate-based, not exact-match** (LLM output varies; the *constraint* is what's
load-bearing). Each case carries `golden.must`, a conjunction over: `tier_is / tier_not /
tier_in / grade_is / grade_in / direction_in`. A misdirection case is typically
`{"tier_not": "HIGH"}`; a positive control `{"tier_is": "HIGH"}`. The case passes iff all
predicates hold on the normalized verdict.

## 3. Eval harness (T1c) — two arms, read-only

**Arm 1 — judge-payload eval (the standing gate arm).** `scripts/evals/run_judge_robustness_eval.py`:
load corpus (synthetic v1 + optionally the mined cases that carry payloads) → for each case call
`grade_holistic(client, case["payload"], include_axis_reads=True)` (real Anthropic client,
JUDGE_MODEL, the diagnostic axis reads ON — it's the eval arm they were built for) → apply
`golden.must` → emit per-class pass/fail table + failing rationales + a machine-readable results
JSON. **Read-only by construction:** touches no DB tables, submits nothing; its only writes are
the results file + stdout. Cost: ~28–110 calls ≈ $3–15 (within the roadmap's $10–30 bound).
Concurrency via one shared `asyncio.Semaphore(3)`; one retry on transport error (not on a wrong
verdict — a wrong verdict IS the datum).

**Arm 2 — full-path replay (deeper, periodic; NOT the gate).** For mined cases with cached raw
corpora (`mi_ep_catalyst_metrics.raw_*`): re-run extraction → rubric → judge to catch
grounding/extraction-layer failures the payload arm can't see. Heavier + needs prod DB reads;
run at M1-review cadence, not per-change. Card C4, sequenced last, can be cut.

**Pass bars (F2 defaults, operator may adjust at sign-off):**
- Hard-misdirection classes (1, 4, 6, 7, 10): **zero** HIGH verdicts tolerated.
- Soft-misdirection classes (2, 3, 8, 9, 11): ≥ 80% per class.
- Positive controls (5, 12 + clean-print): ≥ 80% retain/reach HIGH — the anti-over-skepticism bar.
- Overall: ≥ 85%. Any hard-class failure ⇒ gate FAILS regardless of overall.

## 4. The regression gate (T1e) — mechanical, zero-LLM in the deploy path

**Mechanism (the altitude decision):** the gate does NOT run the LLM eval at deploy time (cost +
nondeterminism in deploys = wrong). Instead it is a **hash-keyed pass record**:

- Running Arm 1 writes `scripts/evals/judge_eval_pass_record.json`:
  `{rubric_version, rubric_hash, catalyst_grade_prompt_version, judge_model, corpus_version,
  run_at, per_class, overall, pass: true|false}`.
- New preflight **[5m/7]** (`scripts/preflight_judge_eval_gate.py`): import the LIVE constants
  (`ep_grade_judge.RUBRIC_HASH`, `RUBRIC_VERSION`, `ep_detector.CATALYST_GRADE_PROMPT_VERSION`,
  `shared.llm_models.JUDGE_MODEL`) and FAIL the deploy iff they differ from the last passing
  record (or the record says `pass: false`). Message: "rubric/model changed — run the judge
  robustness eval first."
- **Deterministic, <1s, no network.** A rubric edit changes `RUBRIC_HASH` automatically (it's
  computed from the text), so *accidental* edits are caught, not just signed ones. A model swap
  changes `JUDGE_MODEL`. Nothing can ship ungraded silently.
- Escape hatch: an operator-signed `waiver: "<reason> <date>"` field in the record (audited by
  the gate's output) — for a true emergency deploy; the gate prints the waiver loudly.

**Scope note:** gate fires only for deploy scopes carrying `agents/market_intelligence/`
(market-agent / both) — orchestrator-only deploys don't re-gate. Corpus lives under `scripts/`
(market-agent-owned in deploy.sh's drift map — corpus edits don't drag 3-service scope).

**Addendum (#509, 2026-07-30/31) — a gap this gate cannot close by construction, closed
elsewhere:** "A model swap changes `JUDGE_MODEL`. Nothing can ship ungraded silently" is
true only for the COMMITTED pin — this gate runs on the HOST at deploy with no API/DB
access, so it can only ever `ast`-parse `shared/llm_models.py`'s literal source. Per the
2026-07-30 operator ruling ("go with the leaders … we can always trace back to when they
were updated"), `JUDGE_MODEL`'s ACTUAL live calls now auto-track the newest opus release
via a nightly-refreshed cache (`shared/llm_models.py` `RESOLVED_ROLES`/`effective_model`)
— a value this gate structurally cannot see, by design (the constant it reads stays a
static literal on purpose; see that file's AUTO-RESOLUTION docstring). The gap is closed
by a SEPARATE nightly in-container guardrail instead:
`agents/market_intelligence/model_resolution.py::check_judge_eval_divergence` compares
what the process is actually running against this pass record's `judge_model` and WARNs
(Telegram + audit, never a deploy block) on drift. This gate's own contract — deterministic,
host-side, blocks on a committed-pin mismatch — is UNCHANGED.

**Addendum (#547, 2026-08-17) — the CALL ENVELOPE is a second, non-blocking signal.**
The gate above fingerprints WHAT we ask the judge (rubric text, model id, corpus) and nothing
about HOW we ask it. On 2026-08-07 it printed *"grade surface unchanged"* on the very deploy
that raised `ep_grade_judge`'s `max_tokens` 500→1500 and added a truncated-verdict fail-open —
two changes that demonstrably moved live grades (7 of 49 verdicts were being built from
truncated responses; two of them promotions to HIGH). `max_tokens`, `timeout`, `tool_choice`
and the transport's fail-open rules all change what grades come out, and none were hashed.

**The fork, and how the operator ruled it (2026-08-13):** folding the envelope into the rerun
fingerprint would force a paid eval on every ceiling tweak. Measured: the judge robustness eval
costs **$3.49/run**, and 08-07 alone — the day three ceilings were raised — would have forced up
to three reruns for changes that never touched the rubric. That spends one paid run per EDIT
where the 2026-08-03 cost rule is one per QUESTION, and the predictable outcome is people
avoiding ceiling fixes to dodge the eval, which is exactly how a caller sat truncating for days.
Operator, verbatim: *"these type of fixes shouldn't cause a rerun"* → **SEPARATE SIGNAL.**

**What ships, therefore:**
- `extract_envelope_keys()` / `check_envelope()` in the same preflight, wholly separate from
  `extract_live_keys()` / `check()`. The **rerun trigger still reads exactly three inputs**
  (rubric version/hash, judge model, corpus sha1) — unchanged, and pinned by a test that proves
  the two are independent in both directions.
- An envelope change **FLAGS LOUDLY and never blocks**: the warning prints FIRST (a skim must
  land on it), names the value and its previous value (`max_tokens: 500 -> 1500`), and the
  final line reads `OK (no eval rerun required) · ENVELOPE CHANGED (see above)` — so
  "unchanged" and "changed but not blocking" can no longer render as the same output. Exit
  code is untouched: `0 if ok else 1`, computed before the envelope is even read.
- deploy.sh `[5m/7]` makes a second cheap `--envelope-audit-json` call and relays the payload
  into `mi_audit_log` via `scripts/log_judge_envelope_change.py` (`|| true` on both — an audit
  row must never fail a deploy).
- Scope is exactly four items: `max_tokens`, `timeout`, `tool_choice`, and a structural hash of
  the transport's truncation/fail-open block. Tool *schema*, `include_axis_reads` and non-live
  timeouts are deliberately OUT.
- ⚠ **Carry-forward risk:** the record's `envelope` sub-key is hand-seeded from static source
  reads (not eval-derived), and nothing in the repo writes the pass record, so a regeneration
  can drop it. It degrades LOUDLY to `UNVERIFIED` — never to a false "unchanged" — but that
  degrade is documented, not gated.

## 5. What feeds #335 / the 7/18 M1 sitting

The first Arm-1 run produces the **robustness map** (per-class failure rates) — the missing
input for the authority decision. Interpretation contract: failures found ≠ block the flip;
they become the R5-preconditions evidence (which classes need a rubric amendment BEFORE
authority vs which are acceptable-with-monitoring). The map + this ADR ride the M1 sitting pack
(Block 3 T5a).

## 6. Amendment loop (T1d) — how failures become fixes without whack-a-mole

Failures cluster by class → ONE rubric amendment per class (not per case), drafted against the
failing rationales → CHANGE_PROCESS (this file + `docs/setups/` grade SSoT) + operator sign-off
→ bump `RUBRIC_VERSION` → **re-run Arm 1 against the SAME corpus** → the fix must clear its
class without dropping the positive-control bar (the over-correction check) → new pass record.
The corpus only grows (cases are never deleted to make a rubric pass — additions need a named
class + golden rationale). Golden cases also hand #301 its seed set (roadmap T1e note).

## 7. Cards (Opus/Sonnet; ~half-day total)

- **C1 — harness** (`run_judge_robustness_eval.py`): loader + predicate scorer + semaphore +
  results/pass-record writer. Pure new file; no live-path change. Tests: predicate scorer truth
  table + a fake-client end-to-end (the `grade_holistic(client=fake)` pattern from existing tests).
- **C2 — preflight [5m/7]** (`preflight_judge_eval_gate.py` + the deploy.sh hook): constants vs
  record compare + waiver print. Tests: match/mismatch/waiver/missing-record (missing = FAIL).
- **C3 — first eval run** (operator-triggered, ~$3–15): produces the robustness map for the M1
  pack + the first pass record (which arms the gate).
- **C4 — Arm-2 full-path replay** (stretch, cut-safe): cached-corpus re-run for the mined cases.
- **Sequencing:** C1 → C3 (map before 7/18) → C2 (gate armed) → C4 whenever. C2 lands only
  after C3 so the gate never blocks on a record that couldn't exist yet.

## 8. Operator forks

- **F1 — corpus sign-off:** the 28 synthetic cases' golden verdicts (esp. the positive
  controls) are judgment calls — skim + sign, or edit individual goldens. *(Rec: sign; every
  golden carries its rationale inline.)*
- **F2 — pass bars:** §3 defaults. *(Rec: accept; tighten after the first map.)*
- **F3 — gate hardness:** [5m/7] as hard-FAIL vs warn-only for its first two weeks. *(Rec:
  hard-FAIL from day one — a warn-only gate is the #173 class: looks armed, isn't. The waiver
  field is the pressure valve.)*
