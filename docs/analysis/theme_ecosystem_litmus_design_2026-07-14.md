# Theme ecosystem → sub-theme design + Marios litmus diagnostic

**2026-07-14 · DESIGN + DIAGNOSTIC only — no code changed, no deploy, read-only prod queries.**
Litmus frame: Marios Stamatoudis (@stamatoudism) two-level UI — ECOSYSTEM (E-\*) → sub-THEMES (T-\*);
his Cybersecurity ecosystem ranks **#2 overall** with a boosted score inherited from **6 sub-themes**
(raw 2.0894 → boosted 2.7540, Δ +0.6646). *(Marios's numbers are operator-provided from his
screenshot — UNVERIFIED against any external source; used as the design target, not as data.)*

Themes are a no-money detection surface, but the **ecosystem taxonomy and the score formula are
operator-signed methodology decisions** — presented in §Operator decisions, not pre-decided.
Any build follows `docs/setups/CHANGE_PROCESS.md` (SSoT update in the same commit, evidence
fields, sign-off on anything that drops/merges themes).

Every quantitative claim below is labeled **[V]** (verified against prod `mi_themes` /
`mi_stock_scores` / `mi_audit_log` on 2026-07-14; queries archived in the session scratchpad,
reproducible from the SQL inline) or **[U]** (unverified / operator-provided / judgment).

---

## PART A — Litmus diagnostic

### A1. Did Apollo DETECT cyber's dominance and resilience? YES. Did it SURFACE it? NO.

**Detection — PASS.**

- **[V] LITMUS 2 (cohort RS)**: weekly avg `rs_composite` of the 15-name cyber cohort
  (CRWD PANW FTNT TENB OKTA CSCO AKAM DDOG ZS S NET CYBR QLYS RPD VRNS):

  | week of | 6/08 | 6/15 | 6/22 | 6/29 | 7/06 | 7/13 |
  |---|---|---|---|---|---|---|
  | cohort RS | 76 | 75 | **62** | 85 | 88 | **89** |

  Confirms the operator's first cut exactly (75 → 62 dip → 85 → 88 → 89). Strength + dip +
  recovery all seen by the raw RS engine. **[V]** Note: only **14 of 15** names have RS rows —
  **CYBR has zero `mi_stock_scores` rows since 6/08** (absent from the scored universe;
  cause not investigated — flagged as a data gap, not assumed).

- **[V] Theme-level detection**: Apollo's one cyber theme, `Network Security & Zero-Trust Edge`,
  has been active 25 of the last 25 snapshot days (6/08 → 7/14), grew 5 → 12 members
  (adding TENB, VRNS, QLYS, RPD, BB, RBRK, CVLT through late June/July), and sits today at
  score 79.4 (of the native 80 cap), rs_avg 98.9, with **11 of 12 members RS ≥ 96.6** (GRRR at
  71 is the only sub-80 member). The theme's rs_avg rank among all active themes: **#1.0 (wk 7/06)
  and #1.5 (wk 7/13)** — Apollo's data says cyber is literally the strongest theme it tracks.

**Surfacing — FAIL, three distinct mechanisms, all verified:**

1. **Drowned in the flood.** **[V]** The theme count exploded 15.6 → 63.1 themes/day (weekly
   averages, §A2), so cyber is one unmarked line among ~45 rendered non-Fading lines. Rank by the
   stored `score` column (the operator's LITMUS 1 — reproduced exactly): 4.3 of 15.6 (wk 6/15) →
   11.8 of 19.8 → 7.8 of 46.7 → 4.0 of 59.9 → 3.0 of 63.1. Top-ish, but nothing marks it as an
   ecosystem-dominant cohort the way Marios's #2-with-6-sub-themes header does.
2. **`/themes` renders Mainstream LAST.** **[V]** `agent.py::_handle_theme_query` (~line 4883)
   groups by stage in order `["Accelerating", "Nascent", "Mainstream"]`. Today's stage counts:
   Accelerating 3, Nascent 15, Mainstream 27, Fading 20. Cyber is Mainstream → it renders at
   roughly line **19-20 of ~45** scored themes, *below* 15 Nascent themes — most of them
   2-3-member July discoveries. (The morning-brief scorecard `briefing.py::_format_theme_scorecard`
   uses `["Accelerating", "Mainstream", "Nascent"]` — cyber ~4th there. The two surfaces disagree;
   the `/themes` order buries the strongest mature theme. Likely unintended — flagged as a
   candidate bug-class fix, no methodology content.)
3. **The June dip was amplified into disappearance.** **[V]** Cyber went stage=Fading 6/23–6/26
   (score dipped to 65.8 on 6/22, rs_avg 71.5 — the real cohort-wide RS dip). `/themes` and the
   scorecard collapse Fading themes into a names-only footnote (`🔻 Fading: …`) — so for 4
   sessions the single strongest month-long theme **did not render as a scored line at all**.
   Marios's UI kept cyber ranked through the same dip (resilience is exactly what his
   ecosystem aggregate shows). Note the frames differ: Apollo RS is *percentile-relative* — the
   cohort really did fall to mid-pack RS 62 that week, so the dip itself is signal, not bug **[U:
   interpretation]** — but a 1-week dip turning the #1 theme into a footnote is a surfacing
   amplification Marios's design doesn't have.

**Member-level coverage divergence from Marios** — **[V]**: of the 15 Marios core names,
today Apollo themes 8 (CRWD FTNT OKTA PANW QLYS RPD TENB VRNS in the cyber theme), 1 adjacent
(DDOG in `Cloud Observability & AIOps`), and **6 have appeared in ZERO `mi_themes` rows since
6/08: ZS, NET, S, CYBR, CSCO, AKAM** (confirmed two ways: correlated-unnest scan and per-ticker
LEFT JOIN count = 0). Current RS: **NET 97.1, S 96.4** (ZS 66, CSCO 66, AKAM 51, CYBR unscored).
Two RS-96+ core cyber names invisible to the theme layer all month is a genuine *detection-coverage*
miss at the member level (the theme was never offered them or validation/assignment never placed
them) — not just a surfacing gap.

**Litmus verdict: detection PASS (RS layer + theme membership growth both saw dominance and
recovery), surfacing FAIL (flood + stage-ordering + Fading-collapse), plus a member-coverage
leak (2 elite names unthemed).**

### A2. The 15 → 63 explosion — real over-fragmentation? Partly — but the "15" baseline was a bug artifact.

Timeline **[V]** (daily active non-Retired counts, `mi_themes` by `theme_date`):
13–15 (6/16–6/24) → 20 (6/25) → 30 (6/26) → 35 (6/29) → 48 (6/30) → 53 (7/02) → 60–65 (July),
2-member themes 4 → 26 over the same span.

Three drivers, each pinned:

1. **Discovery was DEAD before 6/25.** **[V]** `theme_discovered` audit events: **zero** from
   5/11 through 6/21, then ~21/week from the week of 6/22. The fix is commit `482dc50`
   (2026-06-25, "Fix theme-discovery 0-themes truncation — ROOT fix"), following `fc02e97`
   (6/18, max_tokens 1500→4000). So the mid-June "15 themes" the litmus started from was a
   *broken-discovery* state, not a healthy baseline — retirement kept running while births were 0.
   The honest fragmentation frame is **~40 median (the L2 anomaly baseline) → 60-65**, not 15 → 63.
2. **The shadow→live promotion lane opened 6/28.** **[V]** First `shadow_themes_promoted` audit
   event 2026-06-28 13:05 ET (#226, commit `36e7384`, operator-directed). Births by source since
   6/22: **live discovery 53, shadow_promoted 44**. Five active themes today are
   `shadow_promoted`, including a 27-member `Precious Metals Miners & Royalty Streamers` at
   rs_avg 6.
3. **No precision arm live.** **[V]** ADR 0025 (`docs/decisions/0025-theme-fragmentation-controls.md`)
   built dissolve + thesis-merge controls specifically for this flood — **DARK behind
   `THEME_MERGE_ARM` (default OFF)**; corpus eval passed 7/12-13 (14/14 per CLAUDE.md); the flip
   is a pending operator decision. Retirement flow did NOT keep up: births 97 vs retirements 54
   over 4 weeks **[V]**.

**Is it over-fragmentation?** Yes, materially: **[V]** today 26 of 65 active themes (40%) are
2-member; the 7/08 evidence pack (verified consistent with today's data) found 7 sector-families
holding 40 themes with zero-to-near-zero shared tickers (8 insurance, 8 REIT, 7 AI-silicon/quantum…).
**Does it drown dominant themes generally?** Yes — any theme is now 1 line in ~45-65, and the
strongest cohorts are the *mature* ones pushed below the Nascent flood by the `/themes` stage
order. This is not cyber-specific.

*(Count reconciliation: the operator's "89 active" = distinct names with a non-Retired row in the
last 7d **[V: 89]**. `get_active_themes()` (db.py:6248) — latest-row-per-name, drop
latest-Retired — returns **65** today **[V]**. Both real; the engine's own definition is 65.
The 15→63 weekly series in LITMUS 1 used per-day snapshot counts — reproduced exactly **[V]**.)*

### A3. Granularity: is Apollo UNDER-splitting cyber? YES — and the engine itself keeps trying to split it, and gets blocked.

The 12-member blob decomposes cleanly onto Marios's sub-theme axes **[U: mapping is judgment;
membership + RS are V]**:

| Marios sub-theme | Apollo members present | RS today |
|---|---|---|
| Vulnerability & Exposure Mgmt (his global #3) | **TENB, QLYS, RPD** — the exact trio | 99.6 / 99.2 / 99.5 |
| Endpoint Security (his #4) | CRWD, BB (Cylance) | 98.8 / 99.3 |
| Zero-Trust & Identity (his #16) | OKTA (ZS, CYBR never themed) | 99.2 |
| Network security / firewall-SASE | PANW, FTNT | 98.8 / 96.6 |
| Data security & cyber-resilience | VRNS, RBRK, CVLT | 99.3 / 97.3 / 97.9 |
| AI-Native Security (his #7) | GRRR (arguable), DDOG sits in Cloud Observability | 71.2 / 98.3 |

Not one blob — at least 4 distinguishable sub-clusters with elite RS.

**The smoking gun** **[V]** (`mi_audit_log`): the discovery advisor **twice proposed exactly the
Marios split** — 7/07: *"Should I split TENB + RPD + QLYS (all cybersecurity vulnerability
management/exposure platforms) into a specific 'Cyber Vulnerability Management & Exposure
Platforms' sub-theme… distinct from CRWD/PANW/FTNT"*; 7/13: same for TENB, RPD, VRNS, QLYS, BB,
OKTA, CVLT, PANW. Both times the resulting cluster was **killed by Pass1 protect-strip**
(`theme_pass1_protect_strip` 7/07 and 7/13: "stripped N ticker(s) from '<new sub-theme>' to
protect 'Network Security & Zero-Trust Edge'") and **neither name ever persisted a single
`mi_themes` row** **[V]**. Same pattern hit oncology 7/10.

Why, mechanically: the only sanctioned sub-theme creator is the fat-theme split
(`theme_engine.py::_split_fat_theme`), which fires at **> MAX_THEME_STOCKS = 20** members — a
12-member theme never qualifies. Discovery-born sub-clusters are NOT registered in
`sub_theme_parents`, so the parent/child coexistence carve-out (merge pass, ~line 3762) never
protects them; the parent is in `protected_names`, so Pass1 strips the overlap out of the
newborn and it dies below viability. **The hierarchy hooks exist and actively suppress the
granularity Marios has.** And 0 of 65 active themes have `parent_theme` set **[V]**; the last
active-row parent linkage was 2026-05-29 **[V]** — since then `parent_theme` appears only on
synthetic Retired rows, where it means "absorbed into successor" (an overloaded second semantic).

### A4. Other dominant cohorts Apollo currently drowns (quick scan)

**[V]** Keyword-family aggregation over today's 65 active themes, union members joined to latest RS:

| family (hypothetical ecosystem) | themes | union members | union RS avg | members RS≥80 |
|---|---|---|---|---|
| **Cybersecurity** | 1 | 12 | **96** | 11 |
| Biotech/Therapeutics | 7 | 20 | 86 | 15 |
| Insurance | 8 | 36 | 75 | 15 |
| Financials/Fintech | 6 | 39 | 70 | 8 |
| AI-Silicon/Quantum | 5 | 24 | 60 | 4 |
| Energy | 3 | 14 | 55 | 6 |
| REIT | 7 | 31 | 54 | 1 |
| Defense/Space | 3 | 11 | 17 | 0 |

Read: **Biotech/Therapeutics** (7 fragments, 15 RS-80+ members) and **Insurance** (8 fragments,
15 RS-80+ members) are Marios-style ecosystems currently invisible as aggregates — the two
biggest drowned cohorts after cyber. AI-silicon is fragmented (5 themes) but its union RS (60)
says it is genuinely mid-pack right now, not a drowned leader. *(Family keyword mapping is
approximate **[U]**; membership/RS numbers are **[V]**.)*

---

## PART B — Design: the ecosystem → sub-theme borrow (ADR-style)

### B0. Shape

Two-level surface mirroring Marios: **ECOSYSTEM (E-\*)** — a stable, coarse taxonomy of 15–20
buckets — over **sub-THEMES (T-\*)** — the existing emergent `mi_themes` rows, optionally with
parent/child relations *within* an ecosystem for deep ecosystems (cyber). Themes stay the unit of
discovery/validation/lifecycle; ecosystems are a **read-model + score aggregate**, not a new
lifecycle object. Nothing here touches money paths (themes feed briefs + the shadow judge
theme-axis only).

### B1. Components — reusable vs new

**Reusable (verified in code):**
- `parent_theme` column + `sub_theme_parents` dict + merge coexistence carve-out
  (`theme_engine.py:3762`) + `MAX_THEMES_PER_STOCK = 2` ("primary + sub-theme", line 260) —
  exactly the T-level machinery re-granularization needs. Caveat: `parent_theme` is overloaded
  (successor pointer on synthetic Retired rows since ~6/18) — the active-row semantic must be
  documented or the Retired semantic moved to its own column at build time.
- `_split_fat_theme` (line 2896) — the split mechanic (LLM proposes one sub-group, `_score_new_theme`,
  `parent_theme` set, protected from re-absorption). Only its *trigger* (>20 members) is wrong for
  Marios-grade granularity.
- ADR 0025 Arm B's **PARENT_CHILD verdict** — the thesis adjudicator already emits
  "one is a sub-theme of the other → wire via existing sub-theme machinery." This is the natural
  route for the killed discovery-born sub-clusters (A3): instead of Pass1 protect-strip silently
  gutting a newborn that overlaps a protected parent, the pair goes to the (already-built,
  corpus-cleared) adjudicator, which can rule PARENT_CHILD → child persists with
  `parent_theme` set. Composes with the flip decision (§B4).
- `mi_theme_merge_cooldowns`, audit shapes, `_canonicalize_theme_names` — reusable as-is.
- Rendering plumbing: `_compute_scored_themes` (briefing.py:632) already computes per-theme comp
  from constituents; the ecosystem aggregate is the same computation over a union list.

**New:**
1. **Ecosystem taxonomy** — repo-owned YAML (`docs/setups/…` or `config/`): `E-code, name,
   description, keyword stems, exemplar tickers`. ~15–20 entries (proposal: E-CYBR cybersecurity ·
   E-AISEMI AI silicon/semis · E-AIINFRA AI cloud/datacenter · E-SAAS enterprise software ·
   E-BIO biotech/therapeutics · E-MEDTECH devices/diagnostics · E-INS insurance · E-BANKFIN
   banks/fintech/brokers · E-REIT real estate · E-ENER energy · E-METAL metals/mining ·
   E-DEF defense/space · E-TRANS transport/logistics · E-CONS consumer/retail · E-INDL
   industrials/power · E-CRYPTO crypto infra · E-COMM media/adtech · E-HLTH healthcare services;
   plus reserved `E-UNASSIGNED`). **[U — operator-owned list, Decision 1]**
2. **Theme→ecosystem mapping** — `mi_theme_ecosystems(theme_name, e_code, method, assigned_at)`.
   Assigned once at theme birth (and backfilled for the 65 actives) by a Haiku call given the fixed
   taxonomy + theme name/description/members-with-sectors, `analysis_scratchpad`-first (house
   discipline), fallback `E-UNASSIGNED` surfaced in the brief banner for operator triage. Do NOT
   overload `parent_theme` for this — E-level is a classification, not a theme.
3. **Ecosystem score + boost** (§B3) — computed at render/snapshot time from live member RS.
4. **Hierarchical surface** — `/themes` v2: ecosystems ranked by boosted score, each header
   `E-CYBR Cybersecurity — raw 96 → boosted 118 (Δ +22) · 12 names · 11 RS80+`, sub-themes nested
   beneath with their global theme rank (Marios's format), Fading sub-themes shown as struck-through
   names *inside their ecosystem* (not a global footnote — fixes A1-3). Stage stays as a per-line
   tag, dropping the stage-grouping that buries Mainstream (fixes A1-2).

### B2. Decision 1 — curated vs emergent ecosystems

**Recommendation: CURATED taxonomy (operator-owned YAML), LLM-assisted assignment, emergent only
via an explicit operator add.**

- For: the E-layer must be *stable* to be a ranking axis (an algorithmic re-clustering that renames
  or re-cuts ecosystems week-to-week destroys the "cyber has dominated for months" readout — the
  litmus itself is a stability claim). Curated = no re-introduced noise, no new LLM drift surface,
  ~18 buckets is small enough to own by hand. Marios's E-layer is visibly curated.
- Against / cost: new ecosystems (e.g. a genuinely novel narrative like 5/28 drones) need an
  operator edit before they can headline; mitigated by `E-UNASSIGNED` triage in the brief +
  "propose-new-ecosystem" advisor note when unassigned count ≥3 in a family.
- The emergent alternative (cluster the 65 themes by thesis-embedding nightly) auto-adapts but
  re-introduces exactly the instability ADR 0025 is fighting at the T-level, one level up.

### B3. The ecosystem score formula (operator methodology decision)

Requirements from the litmus: a deep, broadly-strong ecosystem (cyber) must POP; a shallow
1-theme ecosystem must not masquerade; **fragmentation must not be rewarded** (on today's data a
sub-theme-count boost ranks Insurance's 8 fragments above cyber's 1 blob — verified failure mode,
§Part C).

**Recommended formula (member-union breadth-weighted, boost mirrors Marios's raw→boosted Δ):**

```
members(E) = dedup union of tickers across E's active non-Fading sub-themes
raw(E)     = trimmed_mean(rs_composite of members(E))            # 0-100, same scale as theme comp
strong(E)  = |{m ∈ members(E) : rs_composite ≥ 80}|
depth(E)   = |{T ∈ E : T has ≥3 members (or elite pair) AND theme comp ≥ 85}|

boost(E)   = 0                                if strong(E) < 5   # thin-ecosystem floor
           = min(0.30, 0.04·depth(E) + 0.015·strong(E))          otherwise
boosted(E) = raw(E) × (1 + boost(E))          # display: raw → boosted (Δ), Marios-style
```

- Deduped **member-union** is the base: fragmentation adds no members, so splitting a cohort into
  8 near-dups cannot raise `raw` or `strong` — the anti-gaming property none of max / sum /
  theme-count-weighted formulas have.
- `depth` rewards *validated* multi-sub-theme structure (post-merge-arm, ≥3-member or elite-pair
  sub-themes at comp ≥85) — the Marios "boosted, inherited from Themes" effect.
- `strong(E) < 5 → no boost` stops a 2-member RS-99 micro-theme (e.g. today's `Consumer Fintech &
  Digital Credit`, rs_avg 99, n=2) from masquerading as a dominant ecosystem; it ranks by raw only.
- Replayed on today **[V inputs, arithmetic U]**: cyber raw 96, strong 11, depth 1 → boost .205 →
  **boosted ≈ 116, #1**; post-regranularization (depth 3) → ≈ 123; Insurance raw 75, strong 15,
  depth ~2 → boost capped .30 → ≈ 97; Biotech raw 86, strong 15, depth ~2-3 → ≈ 112 (#2 — defensible:
  15 elite members across 7 themes IS a real ecosystem). Ordering matches the Marios read.
- Rejected alternatives: **max(sub-theme score)** — shallow masquerade, no depth signal;
  **sum** — size dominates (39-member Financials @ RS 70 would outrank 12-member cyber @ 96);
  **pure weighted-avg** — sound base but no pop for depth/breadth (the property Marios's boost
  exists for); **per-sub-theme-count boost** — fragmentation-rewarding (fails Part C).
- Scale landmine at build time **[V]**: `_upsert_promoted_theme` writes `score = rs_avg` (0-100)
  while native themes cap at 80 (momentum ≤50 + news ≤30) — any E-score built on the stored
  `score` column inherits this mismatch. The formula above deliberately uses member `rs_composite`
  directly and ignores `score`.

### B4. Over-fragmentation (A2): does the design need merge/retire tightening too? YES — and it's already built.

Ecosystem grouping alone fixes the *headline* surface (65 lines → ~15-18 ranked ecosystems) but
leaves: 40% 2-member noise inside every ecosystem's nested list, the validation/description cost
of ~97 births/4wk, the daily L2 `theme_count_active` anomaly, and `depth()` mis-counting until
dup families collapse. **Recommendation: flip `THEME_MERGE_ARM` ON (ADR 0025 Arms A+B) as the
companion move** — it is corpus-cleared (14/14) and awaiting exactly this operator flip; its
`theme_fragmentation_resolution` gated review (count ≤55, 2-member share ≤30%) becomes the
precondition for trusting `depth(E)`. Also file (operator-scoped, from A2 evidence): a triage
pass on the promotion lane — 44 of 97 births are `shadow_promoted`, several at rs_avg ≤ 26
**[V]** — e.g. a promote-floor on cohort rs_avg; kept as a listed option, not pre-decided
(#226 was operator-directed).

### B5. Re-granularization mechanics (Decision 2's "how", if signed)

Minimal-diff path, reusing A3's findings:
1. Route Pass1 protect-strip conflicts where the newborn is a **coherent subset of one protected
   parent** to the 0025 Arm B adjudicator; on PARENT_CHILD → persist child with
   `parent_theme=parent`, register in `sub_theme_parents` (coexistence carve-out then already
   protects it). The two killed vuln-mgmt sub-themes (7/07, 7/13) are the acceptance fixture:
   replayed, they must survive as `T-` children of the cyber theme.
2. Lower the deliberate-split trigger for *ecosystem-dominant* themes only: a theme that is its
   ecosystem's sole sub-theme AND has ≥10 members AND ≥8 RS-80+ members qualifies for one
   `_split_fat_theme` call (currently >20 members). Bounded: ≤1 split/theme/night, existing
   `_SPLIT_MIN_STOCKS=3` floor. *(Thresholds are illustrative — N≥10 backtest per CHANGE_PROCESS
   before ship.)*
3. Member-coverage repair rides for free: sub-theme discovery re-opens seats for the unthemed
   elite names (NET 97, S 96) that the 12-member blob + `MAX_THEMES_PER_STOCK` dynamics never
   admitted; verify at build with an assignment probe. CYBR needs the RS-universe gap (A1) fixed
   first — separate small task.

---

## PART C — Litmus validation of the design (the crux)

**Conceptual replay of the proposed design over the past month's real `mi_themes` data:**

- **Grouping-only (Decision 2 = NO):** cyber's ecosystem = 1 sub-theme = the blob renamed.
  `raw(E-CYBR)` = the theme's own trimmed member RS: **[V]** ~96 (7/14), weekly rs_avg-rank
  trajectory 4.4 → 4.3 → 11.8 (dip wk) → 6.0 → **1.0 → 1.5**. With the boost (strong=11, depth=1)
  it posts ≈116 vs Biotech ≈112, Insurance ≈97 → **E-CYBR surfaces #1-#2 of ~15-18 ecosystems
  through July, and never falls out of the ranked list during the June dip** (Fading sub-themes
  stay rendered inside their ecosystem; the union-breadth base recovers by 6/26 — rs_avg 86.8 —
  faster than the stage machinery did). So the headline litmus — "cyber surfaced as a dominant,
  resilient ecosystem" — **PASSES on grouping alone.** It does NOT pass *because of aggregation*;
  it passes because the single blob is itself elite. Honest limit: in the 6/22 dip week Apollo's
  percentile-RS data genuinely ranks cyber mid-pack (rank ~11.8 of 19.8) — an ecosystem layer
  reduces the *amplification* (no disappearance into the Fading footnote) but cannot and should
  not manufacture Marios's "never dipped" readout out of data that dipped. **[V data, U replay
  arithmetic]**
- **But three Marios-parity properties are UNREACHABLE without re-granularization:**
  (1) the **boost is degenerate** — with depth=1 the "inherited from Themes" mechanism has nothing
  to inherit; worse, any formula that leans on sub-theme structure inverts the ranking on today's
  data (Insurance 8 sub-themes vs cyber 1 → naive per-theme boost ranks Insurance above cyber —
  the fragmentation-rewarding failure, which is why §B3's base is member-union);
  (2) the **sub-theme readout doesn't exist** — Marios's actionable view ("Vulnerability & Exposure
  Mgmt is global #3, Hardware Security is #47") requires T-level rows Apollo deliberately kills
  (A3: two vuln-mgmt births protect-stripped to death, 7/07 + 7/13);
  (3) the **resilience narrative** ("6 sub-themes, ecosystem holds while one rotates") is
  structurally impossible with one blob.
- **Verdict: Decision 2 (re-granularize deep ecosystems) is REQUIRED for the Marios borrow to be
  real, not cosmetic** — grouping-only clears the headline litmus but ships a one-bucket ecosystem
  whose boost, nested view, and resilience signal are all vacuous for exactly the ecosystem the
  litmus is about. The evidence says the cost is small: the engine's own discovery already
  proposes the correct splits (A3) — the design mostly has to stop killing them.

---

## Operator decisions (each: recommendation + rationale — sign-off required, none pre-decided)

1. **Decision 1 — curated vs emergent ecosystem taxonomy.**
   **Rec: CURATED** (~18-bucket operator-owned YAML; LLM assigns themes→buckets at birth;
   `E-UNASSIGNED` triage lane). Rationale: the E-layer is a stability/ranking axis — emergent
   clustering re-introduces at E-level the churn ADR 0025 fights at T-level; Marios's own E-layer
   is curated. Cost: novel narratives need an operator YAML edit to headline (mitigated by the
   triage lane).
2. **Decision 2 — scope: group-only vs also re-granularize deep ecosystems.**
   **Rec: BOTH — re-granularization is REQUIRED (Part C), not optional.** Grouping alone passes
   the headline litmus only because cyber's blob is elite; the boost/nested/resilience mechanics —
   the actual borrow — are vacuous at depth=1, and the engine is already trying to create the
   right sub-themes (two vuln-mgmt births killed by Pass1). Mechanism: PARENT_CHILD routing via the
   already-built 0025 adjudicator + a bounded split trigger for sole-sub-theme dominant ecosystems
   (§B5; thresholds get the CHANGE_PROCESS N≥10 treatment before ship).
3. **Ecosystem score formula.**
   **Rec: member-union breadth-weighted with capped depth boost and thin-floor** (§B3):
   `raw = trimmed-mean union-member RS; boost = min(0.30, 0.04·depth + 0.015·strong), zero if
   strong<5; boosted = raw×(1+boost)`. Rationale: dedup-union base makes fragmentation unrewardable
   (the failure mode every theme-count-based formula has on today's data), thin-floor blocks
   2-member masquerade, depth term reproduces Marios's raw→boosted Δ once sub-themes exist.
   Constants (0.30/0.04/0.015/5/85) are illustrative pins for the backtest, not evidence-backed yet.
4. **Companion flip (already pending, restated not re-decided): `THEME_MERGE_ARM` ON** (ADR 0025,
   corpus-cleared). The ecosystem design *depends* on it for a trustworthy `depth()` and a sane
   nested list; without it the E-layer hides 40% 2-member noise rather than fixing it.
5. **Smaller operator calls surfaced by the diagnostic:** (a) `/themes` stage order renders
   Mainstream last — bug-class fix candidate (two surfaces disagree); (b) promotion-lane floor
   (44 shadow-promoted births/4wk, some at rs_avg ≤26); (c) CYBR missing from the RS universe;
   (d) NET/S (RS 97/96) unthemed all month — assignment/coverage probe; (e) `parent_theme`
   double-semantics (active=sub-theme vs Retired=successor) needs a doc note or column split at
   build time.

## Verification appendix

- **[V]** = run 2026-07-14 against prod (`ssh apollo@87.99.134.162 → apollo-postgres`), read-only.
  Key reproducers: LITMUS 1 rank/count = RANK() OVER (PARTITION BY theme_date ORDER BY score DESC)
  weekly-averaged; LITMUS 2 = AVG(rs_composite) weekly over the 15-ticker array; coverage = ticker
  ∈ ANY(tickers) scans since 6/08 (two query shapes, agreeing); explosion timeline = per-day
  non-Retired counts; audit events by `event_type` (`theme_discovered`, `shadow_themes_promoted`,
  `theme_pass1_protect_strip`, `advisor_call`, `theme_low_quality_description`).
- **UNVERIFIED items, explicitly:** Marios's screenshot numbers (rank #2, 2.0894→2.7540) —
  operator-provided; the Apollo-member ↔ Marios-sub-theme mapping table (judgment); GRRR's
  classification as cyber (borderline); boosted-score replay arithmetic (hand-computed from
  verified inputs, no code exists); "cyber renders ~line 19-20" (derived from verified stage
  counts + near-certain within-group rank, not a captured render); the June-dip
  signal-vs-noise interpretation.
