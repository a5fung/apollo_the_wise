# #368 — the crypto→AI-conversion definition: mechanism, fix, historical proof (2026-08-04)

**Trigger**: 5 of the operator's 9 false-positive theme credits are ONE mistake — a crypto miner
converting its power/data-centre footprint to AI compute filed under crypto mining (HUT ×2, WULF,
CLSK, IREN, Apr–Jul). Operator: *"This is the case where crypto miners are converting into AI."*

**Verdict up front**: this was NOT a missing definition. The engine's own 7/08 birth thesis for
"Bitcoin Mining & Crypto Infrastructure Operators" already read, verbatim: *"renewed focus on
bitcoin miners as scarce, large-scale power and data-center landlords for the AI compute boom …
AI/HPC pivot."* The engine KNEW. What failed is that one real phenomenon was born under 8+ names,
the machinery that exists to consolidate near-duplicates never saw the pairs, and the retention
mechanics evicted the converting names from every AI-framed home. Hand-authoring an "AI conversion"
theme would be hypothesis injection (against the north star) AND unnecessary — the engine
discovers this theme roughly weekly; it just cannot keep it.

## The mechanism — four interacting failures, each prod-evidenced

**M1 — Arm-B merge Stage A had no family for either framing (the primary consolidation gap).**
`theme_merge_arm.FAMILIES` (the curated name-stem list that decides which themes can be PAIRED for
thesis adjudication) has no crypto/bitcoin stem and no AI-infra/data-center/GPU stem. The
majority-sector fallback structurally cannot form for converting miners: FMP splits them across
Financial Services (HUT) / Technology (CORZ, CIFR) / blank. Verified: **zero crypto×AI pairs in
the entire `theme_merge_pairs_proposed` audit history** while insurance/REIT/steel pairs ran
nightly. So "Bitcoin Mining & Crypto Infrastructure Operators" (CIFR HUT) and "AI Compute & GPU
Data Center Hosting Operators" (APLD CORZ IREN WULF) coexisted 7/21–7/27 as disjoint shards of one
cohort — Pass-1 overlap merge blind (zero shared members), Arm B never asked.

**M2 — single-print RS pruning split the cohort by recovery speed.** The converts are
crash-recovery names: rs_composite (1M/3M/6M percentile blend) sat under 25 for weeks even while
they gapped +10–20% on AI-lease news. `PRUNE_RS_HARD=25` removes on ONE daily print; on 7/22 —
day 2 of the ignition — APLD (10.3) and IREN (10.7) were pruned from the AI theme *while rising*,
and the soft prune's "3 consecutive days < 35" read IREN's V-shaped ignition (7.4 → 10.7 → 34.5,
tripled in 3 days) as slow decay. Effect: the two fastest RS-recoverers (HUT, CIFR) stayed under
the crypto name as an elite pair; the slower risers churned under AI names that then starved
(`THEME_COVERAGE_MIN=3` strong members unreachable) and died. The RS mechanics — correct for
stable names — SORTED one cohort into "crypto-named survivors" vs "AI-named corpses".

**M3 — validation evicted the converts from the AI framing on legacy business text.**
`_validate_theme_membership` judges static descriptions ("WULF: Bitcoin mining facilities…",
"CORZ: Cryptocurrency mining…") against the theme NAME, with "wrong industry = remove, be
DECISIVE". Mon 7/27: WULF + CORZ removed from 'AI Compute & GPU Data Center Hosting Operators' —
whose own stored thesis literally said *"Bitcoin-miner-to-AI infrastructure"* — → ADR-0025 Arm-A
dissolve at 2 members → theme Retired, 14d cooldowns fencing both names out until 8/10 (live rows
in `mi_validation_cooldowns`). The validator never saw the thesis it was contradicting.

**M4 — the retire counter ran through a held recovery and killed the theme the day AFTER it
recovered.** The hysteresis damper (flip unconfirmed by yesterday) emitted 8/03 as Fading — with
rs_avg 84.9, because the theme had re-qualified healthy (elite pair CIFR 89.6 / HUT 80.2) — and
`_count_consecutive_fading` counted that held row into an unbroken streak of 6 ≥ 5 → **retired
2026-08-04**, the exact day after the recovery confirmed. Prod today: no crypto-mining theme
exists, HUT/WULF/CLSK/IREN/CIFR/RIOT/MARA/CORZ in no theme, and the day's fresh rediscovery ("AI
Data Center Infrastructure Buildout") was absorbed-retired on its first day. The churn loop closes.

Supporting finds (recorded, not fixed here): the 7/09 carryforward sector-outlier strip removed
HUT from its own birth cohort (FinServ singleton vs Tech majority — the same
static-classification-vs-current-driver failure as M3, on FMP sectors); the 7/17 shadow_v2 stream
re-minted the cohort under TWO crypto-framed names in one night with a crypto-beta thesis
("pure-play Bitcoin miners … tied directly to Bitcoin price") — the conversion thesis the live
birth had was overwritten by the re-mint.

## Why the tempting alternatives are wrong

- **Hand-author the "crypto→AI conversion" theme** — hypothesis injection; violates the north star
  ("themes emerge from RS, not hypotheses") and is unnecessary: Lane-1 discovered the correct
  cohort 7/08 (with the correct thesis) and again 7/21 and 8/04; Lane-2 v1 named it exactly
  ("Bitcoin miners pivoting to AI data centers", HUT+IREN, 7/20).
- **Lower the RS floors / lengthen fading** — global threshold surgery for a cohort-specific
  failure; the floors are doing their job on the numbers they see. The replay shows consolidation
  plus trajectory-awareness suffices; blunt loosening retains genuine dead weight everywhere.
- **Auto-refresh ticker descriptions** — the descriptions aren't wrong, they're legacy captions;
  the cheap correct fix is showing the validator the theme's own thesis (which already names the
  conversion), not re-scraping yfinance (the TSEM bad-description incident lives on that road).
- **Is this #471?** No — stated plainly: #471 Phase 2 (THEME_SUBTHEME_ARM, ON in prod) fixes
  Pass-1 **protect-strip newborn kills** (the cyber vuln-mgmt fixtures). This failure class never
  touches that site: the AI shards died by prune/validation/fading, and the framings were never
  even PAIRED. The fixes below ride the same Arm-B machinery #471 leans on (complementary, no new
  lane, no new mechanism class).

## The fixes (all four shipped; themes = no-money surface)

- **F1 — `compute_infra` Stage-A family — ⛔ WITHDRAWN AT ITS GATE, NOT SHIPPED (see the correction appended at the end of this file)** (`theme_merge_arm.py`): one stem entry
  (`crypto|bitcoin|blockchain|digital asset|data.?cent(er|re)|gpu|colocation|hpc|hyperscal|ai
  compute`) appended LAST (first-match-wins ⇒ every existing family byte-identical; AI-semis stay
  in `semiconductor`). No bare `mining|miner` — metals themes can't land here. Stage A only
  PROPOSES; precision stays in Stage B's corpus-cleared driver-based adjudicator (the pass-record
  hash covers the Stage-B prompt+schema only — a Stage-A extension does not invalidate it).
- **F2 — weak-only fading streak** (`_count_consecutive_fading`): only Fading rows with
  `rs_avg IS NULL` (the weak branch's rows) count toward the 5-day retirement; a Fading row WITH
  rs_avg (score-delta fade or hysteresis-held recovery — membership passed the strong floor that
  day) breaks the streak. Bug-class fix: a theme that re-qualifies healthy must not retire off a
  stale streak.
- **F3 — rising-recovery hold on both prune paths** (`_rescore_existing_theme`): a sub-floor
  member whose RS is RISING over the last 6 sessions (newest > oldest, ≥4 points, else prune as
  before) is held, not pruned. Mirrors the birth gate's derived level-OR-rising cell
  (weak-born maturers rise, corpses fall — `theme_birth_gate_derivation_2026-07-27.md`), applied
  to member retention. Falling/data-poor members prune exactly as before; the hold re-checks
  nightly, so wrongly-held dead names exit on their first non-rising sub-floor day.
- **F4 — thesis-aware validation** (`_validate_theme_membership(thesis=…)`): all three callers
  (Mon/Wed/Fri rescore, #266 birth validation, Arm-B post-merge validation) now pass the theme's
  own description; the prompt shows it ("Theme thesis: …") with the instruction to judge against
  the thesis, not the name alone. `_is_garbage` theses are omitted (a bad Perplexity/Haiku blob
  can never shield bad members); the #214 mass-removal tripwire and the operator-protection shield
  are untouched.

## Historical proof (frozen prod data; `scripts/probes/_368_crypto_ai_consolidation_replay.py`)

Data: `_368_boards.tsv` (mi_themes 6/01–8/04, 2,519 rows) + `_368_rs.tsv` (37,567 RS rows, all
themed tickers). $0; the one paid step is `--adjudicate` (~4 Haiku calls ≈ $0.02) which runs the
REAL Stage-B adjudicator on the frozen historical pairs — expected MERGE / MERGE / DISTINCT
(optical-components negative control). Run on the box with the key before deploy.

- **Part 1 (Stage-A replay, old vs new families)**: the crypto×AI pairing exists from **6/01**
  ('Crypto Asset Recovery' × 'AI Data Center Power Infrastructure' all June; the shard pair 'AI
  Compute & GPU…' × 'Bitcoin Mining & Crypto…' every day 7/21–7/24). 69 new pair-slots over the
  window; 28 days displace 1–2 old pairs at the 8-pair budget — an artifact of the replay not
  modeling DISTINCT cooldowns (in production a pair is adjudicated once, then 30d quiet, freeing
  the budget).
- **Part 2 (lifecycle, real RS, 7/20→8/04)**: the CURRENT-mechanics arm reproduces prod's exact
  death sequence — weak-Fading 7/27–7/31, held-Fading (rs_avg 84.9) 8/03, **RETIRED 8/04**. The
  FIXED arm: the 7/21 rediscovery merges in (F1) instead of competing; on **7/22–7/24 all six
  cohort names (APLD CIFR CORZ HUT IREN WULF) sit in the ONE lineage** with 3 strong members
  (healthy); the pullback prunes the falling four 7/27 (correct — they were falling); F2 breaks
  the streak at the 8/03 held recovery; the lineage **SURVIVES to 8/04** and the same-night
  fold-in of the real 8/04 rediscovery leaves it holding APLD CBRS CIFR CRWV HUT — vs prod-actual:
  0 surviving themes, every miner homeless.
- **Part 3 (F3 backtest, CHANGE_PROCESS N≥10)**: 134 prune-shaped member exits (June–Aug,
  mass-evictions excluded); 25 were rising at exit (the hold's population); of the 13 with a full
  10-session outcome window: **10 recovered to RS≥50, 1 limbo, 2 dead — 77% right**, vs the
  falling control the hold still prunes: 31% (20/65) recovered. The 2 wrongly-held dead names were
  re-pruned by the nightly re-check in a median 6 sessions — the FP cost is days of one weak
  member, the FN cost was cohort destruction.
- **Part 4 (F2 blast radius)**: 14 of the window's streak-driven retirements contained a
  healthy-held row in their terminal streak — including 'AI Memory & Storage' (healthy-held SIX of
  its last eight days and still retired) and 'AI Cloud GPU & Datacenter Colocation Platforms'
  (retired 7/21, held 7/14–15 — F2 would have carried it into the merge window). F2 delays or
  prevents these; max cost is a genuinely-dying theme lingering a few extra Fading days.

## The 5 mislabelled alerts — honest coverage

| alert | prod credit | with these fixes |
|---|---|---|
| HUT 5/06 | Crypto Asset Recovery | **Not re-credited.** Pre-dates any cluster-level conversion evidence; no bottom-up mechanism can honestly re-frame May. (The 6/01+ Arm-B pairing of Crypto Asset Recovery × AI DC Power Infra would adjudicate — likely DISTINCT, correctly: crypto-beta vs utility power buildout.) |
| WULF 7/06 | Crypto Asset Recovery | **Near-miss** — the conversion-thesis birth lands 7/08, two days later. The Lane-2 v2 registry (dark, operator-gated) seeds WULF on exactly 7/06. |
| CLSK 7/14 | (no theme) | **Not covered by these fixes** — CLSK never price-clustered with the cohort in the live lanes. The v2 registry joins it 7/14 ("Ex-miners pivoting to AI HPC leases"). |
| HUT 7/20 | Bitcoin Mining & Crypto Infra Operators (Fading) | **Covered** — member of the surviving lineage whose thesis (and, post-merge, adjudicator-chosen name) is the conversion story; the credit reads correctly. |
| IREN 7/20 | (no theme) | **Covered +1 day** — joins the ONE lineage via the 7/21 merge (in prod it joined a shard that died in 6 days). Alert-date credit still misses by one day; the v2 registry catches 7/20 itself (HUT+IREN co-gap). |

So: these fixes make the board KEEP and CONSOLIDATE what Lane 1 finds (2 of 5 alerts credited, the
structure fixed forward); the remaining 3 are exactly what the already-built **Lane-2 v2 registry**
(flag `lane2_grouping_v2`, dark; its replay assembled WULF 7/06 → CLSK 7/14 → HUT/IREN 7/20 under
"Ex-miners pivoting to AI HPC leases") exists for — its flip is operator-gated (grade-affecting,
ADR-0030 judge eval). Likewise the shadow_v2 re-mint churn (7/16–7/17, two duplicate crypto names
in one night) is already solved by consolidation Phase 1's birth gate (`theme_birth_gate` observe →
on retires the stream) — not duplicated here.

## Deploy notes / verify-live

- No flags: F1–F4 are live-on-deploy behavior of a no-money surface (operator rule: no money ⇒
  ship full). Reversion: each fix is a self-contained revert (family entry / streak predicate /
  hold branch / thesis kwarg).
- **Before deploy**: run `--adjudicate` (~$0.02) where the key lives; expected MERGE / MERGE /
  DISTINCT. A DISTINCT on P1-0721 would mean the adjudicator won't consolidate the framings —
  don't deploy F1 without checking, the rest stand alone.
- **Verify-live**: (1) a `theme_merge_pairs_proposed` row pairing a crypto-framed and AI-framed
  theme (first night both exist); (2) a `ticker_prune_held_rising` changelog line in the run log +
  the member visible next day in `mi_themes.tickers`; (3) a validation night on a conversion-style
  theme keeping its members (no `ticker_revalidated_out` against the thesis); (4) no themes
  retiring with an rs_avg-bearing Fading row newest in their streak.


---

# ⛔ CORRECTION — 2026-08-04, same evening: F1 was withdrawn, and the replay claim that rested on it is retracted

The paid pre-deploy gate ran (3 Haiku calls, $0.01–0.03, captured once to
`/tmp/_368_adjudication_results.json`). Real Stage-B verdicts on the frozen historical pairs:

| pair | expected | ACTUAL |
|---|---|---|
| P1 — 2026-07-21 crypto × `AI Compute & GPU Data Center Hosting Operators` | MERGE | **DISTINCT** |
| P2 — 2026-08-04 crypto × `AI GPU Compute Infrastructure & Cloud Services` | MERGE | **PARENT_CHILD** |
| N1 — optical components (negative control) | DISTINCT | DISTINCT ✅ |

**Two things follow, and the second is the one that matters.**

1. **The gate's own stated hold condition fired.** It read: *"a DISTINCT on the 7/21 pair means hold
   F1."* P1 came back DISTINCT.

2. **PARENT_CHILD is not a consolidation on this codebase's own terms, so P2 is not a pass either.**
   `theme_merge_arm.ADJUDICATION_PROMPT_VERSION` — eight lines above the code F1 changes — records the
   operator's 7/12 ruling that v1 *"answered PARENT_CHILD to pure slices, which keeps both themes and
   leaves the fragmentation (#274's whole purpose) unfixed."* Both themes survive a PARENT_CHILD. And
   the verdict has nowhere to be written: `parent_theme` + `sub_theme_parents` persistence is ADR 0032
   Phase 2 = **#471, not built**.

**So F1 delivers zero consolidation on both historical pairs and is withdrawn.** `theme_merge_arm.py`
is unchanged in the shipped diff; the family and its 6 tests are removed, with the reasoning left in
place at the top of `tests/test_theme_crypto_ai_consolidation.py`. Filed as **#529**, gated on #471.

**RETRACTED with it: the replay's headline consolidation claim** — *"7/21 rediscovery merges instead of
competing; 7/22–7/24 all six cohort names in ONE lineage."* That rested on a SIMULATED merge at 7/21
which the real adjudicator does not give. The simulator's fidelity check (reproducing prod's exact 8/03
held-row → 8/04 death) still stands, and F2/F3/F4's evidence is untouched — none of it depends on a
merge verdict.

**What the gate actually taught us, and it is worth more than F1 was.** The adjudicator consolidates
only when the theme's **thesis text names the conversion**: P2's stored thesis said *"contracted power
capacity and AI/HPC pivots are the driver, not bitcoin price"* → PARENT_CHILD; P1's read as a crypto
theme with one lease headline → DISTINCT. **Thesis quality, not stem families, is the live lever** —
which is exactly what F4 (the validator now reading the theme's own thesis) improves, and exactly what
the separately-filed shadow_v2 re-mint defect degrades by overwriting a correct conversion thesis with
generic crypto-beta text.
