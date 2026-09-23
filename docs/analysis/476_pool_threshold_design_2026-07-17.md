# #476 — theme-engine pool cutoff: why elite orphans aren't homed, and the fix options

**Context:** the per-family biotech cap (#476, shipped 7/17) correctly stopped
biotech themes from being SILENTLY KILLED (cap-0). But it did NOT move the
elite-coverage needle (0/12 night-1), and the forward criterion "≥10/12 in 5
runs" is unachievable as written. This doc traces WHY and lays out the fix
forks with measured costs. **Methodology change → CHANGE_PROCESS + operator
sign-off before anything ships. Nothing built.**

## Root cause: a fixed-COUNT pool cap, exposed by a crowded RS top

The theme engine draws its discovery + assignment pool from `leaders[:40]`
(theme_engine.py:628 shadow, :5024/:5111 live) — the top **40 names by RS
composite**. This is an original heuristic from the first theme commit
(4593ba2), never tuned, no explaining comment. `get_rs_leaders(limit=60)`
fetches 60; discovery/assignment use the top 40.

The flaw: **it's a fixed COUNT, so the effective quality bar floats with how
crowded the top is.**
- Tonight: 123 names at RS≥95, **50 at RS≥98** → the 40th slot is already at
  **RS 98.4**. A name needs RS ≥ 98.4 to be considered.
- A quiet day: the 40th name might be RS 88 → RS-90 names sail in.

A name doesn't become less theme-worthy because 40 OTHERS spiked to 99 today.
The design silently raises its own bar exactly when the market is strongest.

The elite biotech cohort ranks **107–416** (ZBIO 96 = rank 107 … TGTX 83 =
416), so on a crowded day they're shut out of both:
- **Discovery** — though discovery ALSO pulls accelerators/velocity/turners/
  correlation-clusters (broader), the elite don't qualify there either (only
  ZBIO surfaced once in 7d of shadow) → they're strong-but-STATIC, not
  emerging-by-price-action, so discovery legitimately doesn't cluster them.
- **Assignment** (`_assign_uncovered_to_themes`) — draws ONLY from the top-40
  `uncovered` pool → the elite can't be assigned to the EXISTING biotech
  themes they clearly fit (NRIX→protein-degradation w/ GLUE/KYMR;
  ELVN/DNTH/ZBIO→autoimmune w/ SYRE/ORKA). **This is the real, fixable gap.**

Compounding: half the cohort DECAYED since the 7/16 diagnosis (RARE 91→61,
ANNX 86→61, KURA 85→67, ACAD 85→73, TGTX 83) — the "12 elite" is now ~6.

## The measurement that kills the naive fix

"Just use an RS-level bar instead of top-40" balloons the LLM prompt (the
likely original reason for the cap). Uncovered-name counts tonight:

| bar | uncovered names | elite admitted | vs current |
|---|---|---|---|
| top-40 (current) | ~10-15 | 0 | — |
| RS ≥ 95 | 71 | ~1 | 5-7× |
| RS ≥ 90 | 173 | 5 | ~12× |
| RS ≥ 85 | 278 | 7 | ~20× |
| RS ≥ 80 | 381 | 8 | ~25× |

Sector-scoping doesn't rescue it: **96** of the uncovered RS≥85 names are
Healthcare — the elite-12 are 6-8 of a large crowd of strong-but-unclustered
biotech names, not a uniquely-deserving few. Raising the COUNT cap doesn't
reach them until ~top-320 (they start at rank 107).

**Conclusion: there is no cheap pool-tweak. Homing the elite requires either a
much larger prompt, a new bounded mechanism, or reframing the goal.**

## The three real options

### A — blanket pool broadening (lower the bar / raise the count)
Replace top-40 with RS≥85, or raise to top-300. **Cost: 10-25× the discovery/
assignment prompt** (278-381 names + descriptions per night). Over-assigns
(most of the 278 aren't elite). NOT recommended — disproportionate.

### B — a dedicated "sector-orphan crystallization" pass (bounded, targeted)
A SEPARATE nightly step: for each sector with many uncovered strong names
(≥ threshold), make ONE LLM call — "here are the N uncovered RS≥85 {sector}
names, cluster them into coherent sub-themes" — validate + save the result.
- Cost: ~1-5 extra LLM calls/night (one per orphan-heavy sector), NOT 96 names
  bolted onto every prompt. Bounded and cheap.
- Homes the elite by CREATING the theme that holds them (protein-degradation
  cluster, autoimmune cluster) rather than forcing them into the top-40 pool.
- Reuses the existing discovery→validate→save machinery; the only new surface
  is the per-sector orphan selector.
- This is the viable fix IF the operator wants the coverage.

### C — reframe / accept (cheapest; the per-family cap already fixed the bug)
Accept that strong-but-UNCLUSTERED names (rank 100+) don't get themed — the
theme engine themes LEADERS + CLUSTERS by design, and a name earns a theme by
either leading (top-40) or co-moving (a cluster). The elite biotech do
neither right now. The #476 cap fix already stopped the actual DEFECT (silent
biotech-theme kills); homing static-strong names is a scope EXPANSION, not a
bug fix. Close the elite-coverage sub-goal as "working as designed"; the cap
fix stands.

## Recommendation

**C if the elite-coverage was really a proxy for "stop killing biotech themes"
(which the cap fix already solved) — B if the operator specifically wants the
elite cohort surfaced as a theme.** Not A (cost). The forward criterion should
be dropped or rewritten either way (the ≥10/12-in-5-runs bar can't be met by
the shipped change).

Operator fork: **B (build the bounded orphan-crystallization pass) or C
(reframe + close the sub-goal, cap fix stands)?**


## Advisor-refined design (2026-07-17) + validation path

Consulted the advisor on threshold + design. Three refinements (shape, not
direction):

1. **Floor AND ceiling, not a pure level.** `leaders[:CEILING]` (≈200) then
   filter `RS≥90`. RS≥90 binds on normal/crowded days; the ceiling is a tail
   backstop so a euphoric tape can't balloon the pool (the failure the original
   count-cap crudely prevented). RS composite is percentile-based (somewhat
   self-normalizing) but the top-tail crowding is real — keep the ceiling.
2. **Widen the ASSIGNMENT pool only, not discovery.** The assignment pass is
   the diagnosed gap; discovery legitimately shouldn't force-cluster static
   singletons and already has velocity/turners/correlation-clusters for
   genuinely-emerging names. Global-swap risks marginal NEW themes from ~83
   discovery candidates. Assignment-only is lower-risk and fixes what's broken;
   a real new cluster still gets discovered via the correlation-cluster pool.
3. **Validate before deploy; let the validation pick the threshold.** This is a
   criterion change that feeds EP selection (theme axis → HIGH tier, ADR 0015)
   and widens the correlated-book surface (R1). Don't argue 90/92/85 — observe
   the actual theme output.

**Facts confirmed:** raising the theme-engine `leaders` fetch 60→200 is safe
(screener/rs_engine/sector-map already call limit=200); description cost ≈12
Haiku calls worst-case (uncached only); the REAL RS≥90 uncovered pool via the
liquidity-filtered fetch is **83** (not the raw 173) — smaller, better.

**Validation attempt (inconclusive):** a standalone `_assign_uncovered_to_themes`
dry-run on tonight's data returned 0/83 assigned with NO error logged — but the
harness hit yfinance description failures, so it likely didn't feed the LLM
descriptions faithfully (the live path pre-populates them). A hacked harness is
the wrong tool for a criterion change anyway.

**The disciplined validation = the codebase's proven build-dark-then-flip
pattern** (THEME_SUBTHEME_ARM / THEME_MERGE_ARM idiom): build the
assignment-pool widening (floor RS≥90 + 200-ceiling) behind a DB toggle,
default OFF (byte-identical), deploy dark, log the assignment DIFF (top-40 vs
RS≥90) on a live nightly run, and let the operator lock the threshold from that
real diff before flipping. Settles 90/92/85 empirically on faithful output,
validates it produces sane assignments not junk, and the flip is operator-gated
+ reversible — exactly the discipline a theme criterion feeding EP selection
warrants.

**NEXT (a real build, own session):** the toggle + `assignment_pool_arm` +
the shadow-diff logging → deploy dark → one nightly → operator reads the diff →
flip or tune. NOT tonight (methodology change, careful build).
