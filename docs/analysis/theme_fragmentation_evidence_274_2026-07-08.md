# #274 theme-fragmentation — EVIDENCE PACK (feeds the weekend Fable design)

**2026-07-08 · read-only · cohort = today's active themes (`274_themes_2026-07-08.json`, 63 non-Retired) + cooldowns/21d (`274_cooldowns_2026-07-08.json`, 34).**  

Data-backing: the 7/8 L2 anomaly (theme_count_active 78 vs 40 median). This pack quantifies each scoped lever's effect + a legit-kill surface — it is EVIDENCE for the Fable design, NOT a fix. Every lever = detection-criterion → SSoT + CHANGE_PROCESS + operator sign-off + N≥10 backtest; ADR 0007 §3 anti-noise caveat (don't reintroduce the nascent-miss) governs all of it.


## The shape of the problem

- Member-count distribution: 2m: 27 · 3m: 7 · 4m: 10 · 5m: 6 · 6m: 7 · 7m: 1 · 8m: 1 · 12m: 1 · 13m: 1 · 15m: 1 · 20m: 1

- **27 of 63 active themes are 2-member (43%)** — the fragmentation core.

- 27 themes have <3 members; 34 have <4.


## L1 — dissolve-on-flagged-pair (#274's original fix)

2-member themes that have had a member churned by validation (cooldown history) — the immortality-risk set the fix targets: **7** of 27.

| theme | members | flagged member(s) |
|---|--:|---|
| Domestic Steel Producers | 2 | RS |
| Industrial Power Equipment & Electrical Systems | 2 | CAT |
| Pure-Play Quantum Computing Hardware | 2 | QUBT, SKYT |
| Quantum Computing Hardware & Annealing Systems | 2 | QUBT |
| Quantum Computing & Quantum-Safe Networking | 2 | HQ |
| Satellite Communications & Space Data Services | 2 | GD, RTX |
| SMB & Workforce Business Services Platforms | 2 | FA |

> Leverage: NARROW — only 7 themes. Dissolve-on-flag catches the *unstable* 2-member themes, not the *stable-but-thin* bulk. Necessary, not sufficient.

## L2a — lower the shared-ticker merge threshold (today MIN_SHARED_FOR_MERGE=3)

Theme pairs sharing ≥2 tickers (would merge if threshold dropped 3→2): **2**. Pairs sharing exactly 1: 0.

| theme A | theme B | shared |
|---|---|---|
| In Vivo Gene & Engineered Cell Therapy Clinical Re-Rating | Rare & Orphan Disease Biotech | RGNX, SRRK |
| Non-US & Frontier Market Digital Financial Services Re-Rating | Global Digital Payments & Cross-Border Fintech | PAYP, WSE |

> Leverage: MODEST — the visible near-dups (insurance/REIT) are ticker-DISJOINT (distinct names), so a lower shared-ticker threshold does NOT merge them. That's why L2b (sector arm) exists.

## L2b — sector/narrative merge arm (merge on family even with <3 shared tickers)

Sector-families with ≥2 active themes: **7** families holding **40** themes → would collapse toward ~7 (one per family, modulo genuine sub-industry distinctions). Net reduction on the order of **33** themes.

| family | # themes | max shared tickers (why shared-merge misses them) | themes |
|---|--:|--:|---|
| Insurance | 8 | 0 | Property & Casualty Insurance Underwriters, Life Insurance & Annuity Providers, Private Mortgage Insurance, Specialty Insurance Underwriting & Brokerage (+4 more) |
| REIT / Real Estate | 8 | 0 | Open-Air & Strip Mall Retail REITs, Coastal & Suburban Residential Rental REITs, Senior & Long-Term Care Healthcare REITs, Commercial Real Estate Brokerage & Advisory Services (+4 more) |
| AI silicon / Datacenter / Quantum | 7 | 0 | Semiconductor Wafer Foundry & Advanced IC Manufacturing, Custom AI Silicon & Chip Architecture Licensing, AI Cloud GPU & Datacenter Colocation Platforms, Pure-Play Quantum Computing Hardware (+3 more) |
| Biotech / Therapy | 7 | 2 | Peptide & Hormone Therapies for Metabolic & Endocrine Disorders, In Vivo Gene & Engineered Cell Therapy Clinical Re-Rating, Rare & Orphan Disease Biotech, Genomic Medicine & Synthetic DNA Tools (+3 more) |
| Fintech / Payments / Brokerage | 5 | 2 | Wealth Management & Retail Brokerage Platforms, Non-US & Frontier Market Digital Financial Services Re-Rating, B2B Digital Financial Infrastructure & Payment Rails Modernization, Global Digital Payments & Cross-Border Fintech (+1 more) |
| Cloud / Security / Adtech | 3 | 0 | Network Security & Zero-Trust Edge, Cloud Observability & AIOps Monitoring Platforms, Digital Advertising Technology Platforms |
| Energy / Oil | 2 | 0 | U.S. Petroleum Refining & Downstream Processing, Oilfield Pressure Pumping & Completion Services |

> Leverage: **HIGHEST** — this is the mechanism for the operator-visible dups. LEGIT-KILL RISK: some same-family themes are genuinely distinct sub-industries (P&C vs specialty-catastrophe insurance; office vs multifamily REIT) — the design must merge on THESIS coherence, not just the family keyword, or it collapses real distinctions. This is the core Fable judgment call.

## L3 — birth min-member floor

- Floor = 3 → dissolves/blocks **27** themes (43% of the cohort).

- Floor = 4 → **34** themes (54%).

LEGIT-KILL surface — the sub-3-member themes (Fable/operator eyeball which are real vs noise; ADR 0007's 26-theme corpus was ~27% noise → most may be legit small themes):

  - (2m, Fading) Alternative Asset Management Platforms
  - (2m, Mainstream) Casual Dining Restaurant Turnaround
  - (2m, Nascent) Cloud Observability & AIOps Monitoring Platforms
  - (2m, Nascent) Consumer Fintech & Digital Credit Platforms
  - (2m, Nascent) Digital Advertising Technology Platforms
  - (2m, Nascent) Digital Insurance Distribution & Marketplace Platforms
  - (2m, Fading) Domestic Steel Producers
  - (2m, Nascent) Genomic Medicine & Synthetic DNA Tools
  - (2m, Nascent) Golf Equipment & Apparel
  - (2m, Fading) Government-Funded Senior & Post-Acute Care Re-Rating
  - (2m, Fading) Industrial Power Equipment & Electrical Systems
  - (2m, Mainstream) Inflammatory Disease & Immunology Biologics
  - (2m, Fading) Insurance Brokerage & Risk Advisory
  - (2m, Fading) Large-Cap U.S. Defense Primes
  - (2m, Nascent) Liquid Biopsy & Multi-Cancer Early Detection
  - (2m, Fading) Precious Metals Miners (Gold & Silver)
  - (2m, Fading) Precision Aerospace & Defense Component Manufacturers
  - (2m, Fading) Precision Optics & Photonic Components
  - (2m, Nascent) Pure-Play Quantum Computing Hardware
  - (2m, Fading) Quantum Computing & Quantum-Safe Networking
  - (2m, Fading) Quantum Computing Hardware & Annealing Systems
  - (2m, Nascent) SMB & Workforce Business Services Platforms
  - (2m, Fading) Satellite Communications & Space Data Services
  - (2m, Fading) Semiconductor Probe Card & Front-End Test Equipment
  - (2m, Fading) Senior Living & Housing Operators
  - (2m, Nascent) Specialty Catastrophe Property Insurance Underwriters
  - (2m, Nascent) Targeted Protein Degradation Oncology

> Leverage: BROAD but BLUNT — a flat floor is exactly what was deliberately rejected (theme_engine.py:1879, 'description-guard not 2-member cap') because it kills legit small themes. If revisited, gate it on the ADR 0007 §3 anti-noise metric (validated-themes/day) + a nascent-recall check, not a bare count.

## Read for the Fable design

- **Highest leverage = L2b** (sector/narrative merge arm) — it targets the operator-visible near-dup clusters that the shared-ticker merge structurally misses (they're ticker-disjoint). The hard part is THESIS-coherence merging without collapsing real sub-industry distinctions.

- **L1 (dissolve-on-flag)** is a cheap, safe complement — narrow but pure-signal.

- **L3 (min-member floor)** is the riskiest (legit-kill) and was already rejected once; only revisit gated on the anti-noise metric, not a bare count.

- All three are ASYMMETRIC-safe if merges/dissolves require validation/thesis evidence — never a blind count. THE LINE: no live theme-engine change without SSoT + CHANGE_PROCESS + sign-off.


_Reproduce: `python scripts/probes/_274_fragmentation_evidence.py` off the two cached JSONs._
