# #657 — co-movement as a REMOVAL rule: results (2026-09-24 board, judged on the 60 sessions to 2026-09-24)

## 1. Population — today's board

| population | n |
|---|---|
| themes on the 2026-09-24 board (7-day mirror of get_active_themes, Retired dropped) | 109 |
| memberships (ticker, theme) | 704 |
| … judgeable by the tape (≥3 basket members with history, ≥30 overlapping sessions) | 608 (86% of 704) |
| … NOT judgeable → the sector test keeps deciding (fail-safe) | 96 {'unjudgeable:thin_basket': 96} |
| themes the rule cannot touch at all (every member unjudgeable — a 3-member theme leaves a 2-name basket after leave-one-out) | 36 of 109 (every theme with an unjudgeable member: 36) |
| **Shape B evictions: judgeable memberships below 0.35** | **52 of 608 (9%)** |
| themes with ≥1 eviction | 22 of 109 |
| themes an eviction pass would leave under 3 members | 2 of 22 changed themes |
| themes it would leave under PRUNE_MIN_TICKERS=2 (retired next pass) | 1 of 22 |
| evictions inside a PAYING theme (Accelerating/Mainstream — a LISTED member gets the EP +10 regardless of co-movement) | 18 of 52 (18 distinct stocks) |

### Provenance of the evictions (each n is of the eviction list)

| join path (first audit event naming the pair, rename lineage followed) | n |
|---|---|
| assignment_llm | 27 of 52 |
| merge:unlogged | 15 of 52 |
| shadow_promoted | 5 of 52 |
| unknown | 4 of 52 |
| merge:merge_pass_successor | 1 of 52 |

| how the pair got onto the board | n |
|---|---|
| an LLM judged THIS pair at join (assignment proposal + immediate validation, discovery/split + birth validation) | 27 of 52 |
| the MERGE MACHINERY moved it in (thesis merge / Pass 1.5 absorption / sub-theme merge / merge-pass successor / birth-gate join) — no LLM judged the pair at join | 16 of 52 |
| a Lane-2 shadow cohort was promoted whole | 5 of 52 |
| untraceable | 4 of 52 |

| membership-LLM / operator flags | n |
|---|---|
| passed the membership LLM at least once (validated at join, or survived ≥1 Mon/Wed/Fri rescore) | 50 of 52 (96%) |
| … validated at join (assignment / discovery / split path) | 27 of 52 |
| … survived ≥1 Mon/Wed/Fri rescore after joining | 50 of 52 |
| … survived ≥3 rescores | 48 of 52 |
| operator placed or confirmed (operator-promoted theme ticker, or bypassed cooldown) | 0 of 52 |
| one of the 09-13 backtest's 95 assignment-night pairs | 16 of 52 |
| median days on the board (join → 2026-09-24) | 16 |

### What the strips the engine ALREADY runs would do with the same names

| overlap check | n |
|---|---|
| evictions that are SINGLETON-sector members (the carry-forward label strip removes these tomorrow anyway) | 1 of 52 |
| evictions with an Unknown sector (the label never touches them) | 0 of 52 |
| evictions the label leaves alone (same-sector, known) — reachable ONLY by Shape B | 51 of 52 |

### Shape A — as built (`comove_ctx` passed to the two strip sites): singleton-sector members only

| singleton-sector members on today's board | n |
|---|---|
| singleton-sector members (what the label strips tonight without the context) | 8 of 704 memberships |
| … the tape would KEEP (≥ 0.35) | 7 of 8 |
| … the tape would STRIP (< 0.35) — the label strips these too | 1 of 8 |
| … unjudgeable → stripped by the label as before | 0 of 8 |

| stock | theme | stage | sector | reading | tape says |
|---|---|---|---|---|---|
| OKLO | Small Modular Reactor & Advanced Nuclear Fission Techno | Nascent | Utilities | 0.90 | admit |
| LEU | Small Modular Reactor & Advanced Nuclear Fission Techno | Nascent | Energy | 0.84 | admit |
| MAS | Home Improvement Retail & Building Products | Nascent | Industrials | 0.68 | admit |
| PUBM | Digital Advertising & Ad-Tech Monetization Platforms | Mainstream | Technology | 0.66 | admit |
| TNET | Enterprise HR & Workforce Management SaaS | Mainstream | Industrials | 0.61 | admit |
| VSAT | Space Economy: Satellite Communications & Launch Servic | Mainstream | Technology | 0.49 | admit |
| WLTH | Wealth Management & Retail Brokerage Platforms | Mainstream | Technology | 0.40 | admit |
| AGRO | Global Agriculture Value Chain Recovery | Mainstream | Consumer Defensive | 0.09 | reject |

### The churn the split ruling creates (job 1 admits on the tape, job 2 strips on the label)

| since 2026-09-13 | n |
|---|---|
| pairs the tape admitted OVER the sector label (`assignment_comove_admitted_over_sector`) | 21 distinct pairs (33 events) |
| … stripped again by the label as `sector_outlier` within 7 days | 16 of 21 |
| … re-admitted over the label ≥2 times (the loop) | 9 of 21 |

| night | stock | theme | admitted at | stripped by label after (days) | times admitted |
|---|---|---|---|---|---|
| 2026-09-15 | BAH | Defense Intelligence & Cybersecurity IT Contractor | 0.73 | 1 | 3 |
| 2026-09-17 | BAH | Defense Intelligence & Cybersecurity IT Contractor | 0.69 | 1 | 3 |
| 2026-09-21 | BAH | Defense Intelligence & Cybersecurity IT Contractor | 0.74 | — | 3 |
| 2026-09-23 | BLSH | Bitcoin Holding & Trading Proxy Equities | 0.67 | 1 | 1 |
| 2026-09-18 | BTDR | Bitcoin Mining Stocks Rotation Reversal | 0.78 | 3 | 2 |
| 2026-09-22 | BTDR | Bitcoin Mining Stocks Rotation Reversal | 0.81 | — | 2 |
| 2026-09-16 | BTU | Metallurgical & Thermal Coal Mining Rebound | 0.72 | 1 | 1 |
| 2026-09-21 | BXC | Homebuilders & Residential Construction Supply Cha | 0.37 | 1 | 1 |
| 2026-09-22 | CCS | Homebuilders & Residential Construction Supply Cha | 0.76 | 1 | 1 |
| 2026-09-16 | ECO | Crude & Product Tanker Shipping | 0.80 | — | 1 |
| 2026-09-23 | ENSG | Skilled Nursing & Senior Housing Healthcare REITs | 0.60 | 1 | 1 |
| 2026-09-18 | GOLD | Gold & Precious Metals Miners Rotation | 0.53 | — | 1 |
| 2026-09-22 | GOLD | Precious Metals Complex Rebound | 0.54 | — | 1 |
| 2026-09-15 | GPN | B2B Digital Financial Infrastructure & Payment Rai | 0.75 | 1 | 1 |
| 2026-09-16 | IRDM | Space Economy: Satellite Communications & Launch S | 0.43 | 1 | 3 |
| 2026-09-18 | IRDM | Space Economy: Satellite Communications & Launch S | 0.40 | 3 | 3 |
| 2026-09-22 | IRDM | Space Economy: Satellite Communications & Launch S | 0.41 | 1 | 3 |
| 2026-09-21 | MLAB | Life Science Tools & Analytical Instruments | 0.66 | 1 | 2 |
| 2026-09-23 | MLAB | Life Science Tools & Analytical Instruments | 0.64 | 1 | 2 |
| 2026-09-15 | MSTR | Bitcoin Treasury & Crypto Proxy Equities Correlati | 0.78 | 1 | 2 |
| 2026-09-23 | MSTR | Corporate Digital Asset Treasury Vehicles | 0.87 | 1 | 2 |
| 2026-09-23 | NBIS | Emerging AI Compute & Cloud Infrastructure Platfor | 0.73 | 1 | 1 |
| 2026-09-24 | PUBM | Digital Advertising & Ad-Tech Monetization Platfor | 0.58 | — | 1 |
| 2026-09-22 | TNET | Enterprise HR & Workforce Management SaaS | 0.64 | 1 | 2 |
| 2026-09-24 | TNET | Enterprise HR & Workforce Management SaaS | 0.62 | — | 2 |
| 2026-09-18 | UMAC | Space Economy: Satellite Communications & Launch S | 0.64 | — | 1 |
| 2026-09-21 | VICR | On-Site Power Generation & Distribution Equipment  | 0.64 | 1 | 2 |
| 2026-09-23 | VICR | On-Site Power Generation & Distribution Equipment  | 0.62 | 1 | 2 |
| 2026-09-17 | VSAT | Space Economy: Satellite Communications & Launch S | 0.52 | 1 | 3 |
| 2026-09-21 | VSAT | Space Economy: Satellite Communications & Launch S | 0.47 | 1 | 3 |
| 2026-09-24 | VSAT | Space Economy: Satellite Communications & Launch S | 0.45 | — | 3 |
| 2026-09-18 | WLTH | Wealth Management & Retail Brokerage Platforms | 0.36 | 3 | 2 |
| 2026-09-24 | WLTH | Wealth Management & Retail Brokerage Platforms | 0.41 | — | 2 |

## 2. The eviction list (Shape B, today's board)

Every judgeable membership below 0.35. LLM = passed the membership LLM at least once; op = operator placed/confirmed; single = singleton-sector (the label strips it anyway); pay = paying-stage theme; bt95 = in the 09-13 backtest's 95.

| stock | theme | stage | reading | basket | sector | joined | path | rescores | LLM | op | single | pay | bt95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HTFL | AI-Driven Diagnostics & Imaging Re-Rating | Mains | 0.12 | 8 | Healthcare | 2026-08-21 | merge:unlogged | 13 | y | — | — | y | — |
| CDNA | AI-Driven Diagnostics & Imaging Re-Rating | Mains | 0.15 | 8 | Healthcare | 2026-08-25 | assignment_llm | 12 | y | — | — | y | y |
| DGX | AI-Driven Diagnostics & Imaging Re-Rating | Mains | 0.28 | 8 | Healthcare | 2026-09-03 | assignment_llm | 8 | y | — | — | y | y |
| LH | AI-Driven Diagnostics & Imaging Re-Rating | Mains | 0.29 | 8 | Healthcare | 2026-09-03 | assignment_llm | 8 | y | — | — | y | y |
| ORCL | AI-Powered Enterprise Analytics & Intelligent Wo | Fadin | -0.14 | 17 | Technology | 2026-09-08 | assignment_llm | 7 | y | — | — | — | y |
| MSFT | AI-Powered Enterprise Analytics & Intelligent Wo | Fadin | 0.19 | 17 | Technology | 2026-09-01 | assignment_llm | 9 | y | — | — | — | y |
| DB | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.22 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| BCS | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.24 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| MFG | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.24 | 44 | Financial Serv | 2026-09-17 | assignment_llm | 3 | y | — | — | — | — |
| BBVA | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.25 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| SAN | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.28 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| C | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.31 | 44 | Financial Serv | 2026-09-16 | assignment_llm | 3 | y | — | — | — | — |
| LYG | Bank Stocks: Rising-Rate NIM Expansion | Fadin | 0.34 | 44 | Financial Serv | 2026-09-14 | merge:unlogged | 4 | y | — | — | — | — |
| IOND | Bitcoin Mining Stocks Rotation Reversal | Mains | 0.18 | 9 | Financial Serv | 2026-09-11 | shadow_promoted | 5 | y | — | — | y | — |
| APLD | Cloud Data Storage & Analytics Infrastructure | Mains | -0.18 | 3 | Technology | 2026-09-17 | merge:unlogged | 3 | y | — | — | y | — |
| ESTC | Cloud Data Storage & Analytics Infrastructure | Mains | 0.26 | 3 | Technology | 2026-08-13 | assignment_llm | 17 | y | — | — | y | — |
| ARHS | Commercial, Office & Home Furniture Retailers an | Fadin | 0.33 | 4 | Consumer Cycli | 2026-08-18 | assignment_llm | 15 | y | — | — | — | — |
| SR | Crude & Product Tanker Shipping | Mains | 0.10 | 12 | Utilities | 2026-09-24 | merge:unlogged | 0 | n | — | — | y | — |
| ATO | Crude & Product Tanker Shipping | Mains | 0.27 | 12 | Utilities | 2026-09-24 | merge:unlogged | 0 | n | — | — | y | — |
| EMBJ | Defense Electronics & Aerospace Subsystem Suppli | Mains | 0.09 | 8 | Industrials | 2026-08-11 | unknown | 18 | y | — | — | y | — |
| RTX | Defense Electronics & Aerospace Subsystem Suppli | Mains | 0.16 | 8 | Industrials | 2026-08-11 | unknown | 18 | y | — | — | y | — |
| EFOR | Defense Intelligence & Cybersecurity IT Contract | Mains | 0.19 | 6 | Technology | 2026-08-19 | shadow_promoted | 14 | y | — | — | y | — |
| VVX | Defense Intelligence & Cybersecurity IT Contract | Mains | 0.34 | 6 | Industrials | 2026-09-21 | assignment_llm | 1 | y | — | — | y | — |
| TBBB | Defensive Consumer Staples Rotation | Fadin | 0.19 | 16 | Consumer Defen | 2026-08-28 | assignment_llm | 10 | y | — | — | — | y |
| GO | Defensive Consumer Staples Rotation | Fadin | 0.32 | 16 | Consumer Defen | 2026-08-25 | assignment_llm | 12 | y | — | — | — | — |
| MGNI | Digital Advertising & Ad-Tech Monetization Platf | Mains | 0.26 | 3 | Communication  | 2026-09-14 | assignment_llm | 4 | y | — | — | y | — |
| HNRG | Diversified Power Generation Capacity Expansion  | Fadin | 0.17 | 4 | Utilities | 2026-09-08 | shadow_promoted | 7 | y | — | — | — | — |
| AES | Diversified Power Generation Capacity Expansion  | Fadin | 0.20 | 4 | Utilities | 2026-09-16 | assignment_llm | 3 | y | — | — | — | — |
| EVRG | Diversified Power Generation Capacity Expansion  | Fadin | 0.28 | 4 | Utilities | 2026-09-15 | unknown | 4 | y | — | — | — | — |
| OGE | Diversified Power Generation Capacity Expansion  | Fadin | 0.33 | 4 | Utilities | 2026-09-08 | shadow_promoted | 7 | y | — | — | — | — |
| FTK | Energy Infrastructure & Services Complex | Fadin | 0.01 | 15 | Energy | 2026-09-15 | merge:merge_pass_successor | 4 | y | — | — | — | — |
| WKC | Energy Infrastructure & Services Complex | Fadin | 0.12 | 15 | Energy | 2026-09-16 | assignment_llm | 3 | y | — | — | — | — |
| NTNX | Enterprise Server, Storage & Data Infrastructure | Nasce | -0.19 | 7 | Technology | 2026-08-17 | assignment_llm | 15 | y | — | — | — | y |
| ITUB | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.17 | 21 | Financial Serv | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| XP | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.20 | 21 | Financial Serv | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| CHYM | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.28 | 21 | Technology | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| PGY | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.34 | 21 | Technology | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| KSPI | Fintech & Digital Finance Sector Re-rating on Fe | Fadin | 0.34 | 21 | Technology | 2026-09-16 | merge:unlogged | 3 | y | — | — | — | — |
| QURE | Genetic Medicine: Gene Editing & Gene Therapy In | Fadin | 0.29 | 3 | Healthcare | 2026-09-02 | assignment_llm | 8 | y | — | — | — | y |
| AGRO | Global Agriculture Value Chain Recovery | Mains | 0.09 | 3 | Consumer Defen | 2026-09-02 | unknown | 8 | y | — | y | y | — |
| ACA | Industrial Construction Execution & On-Site Supp | Fadin | -0.16 | 7 | Industrials | 2026-09-09 | assignment_llm | 6 | y | — | — | — | y |
| TTEK | Industrial Construction Execution & On-Site Supp | Fadin | -0.12 | 7 | Industrials | 2026-08-21 | assignment_llm | 13 | y | — | — | — | y |
| J | Industrial Construction Execution & On-Site Supp | Fadin | -0.08 | 7 | Industrials | 2026-08-11 | assignment_llm | 18 | y | — | — | — | — |
| KBR | Industrial Construction Execution & On-Site Supp | Fadin | 0.12 | 7 | Industrials | 2026-08-20 | assignment_llm | 14 | y | — | — | — | y |
| AGX | Industrial Construction Execution & On-Site Supp | Fadin | 0.20 | 7 | Industrials | 2026-09-14 | assignment_llm | 4 | y | — | — | — | y |
| TRAX | Inflammatory Disease & Immunology Biologics | Fadin | 0.22 | 8 | Healthcare | 2026-09-08 | assignment_llm | 7 | y | — | — | — | y |
| AUPH | Inflammatory Disease & Immunology Biologics | Fadin | 0.30 | 8 | Healthcare | 2026-08-20 | assignment_llm | 14 | y | — | — | — | — |
| INSP | Medical Device Mean-Reversion & Rotation Recover | Fadin | 0.21 | 13 | Healthcare | 2026-07-20 | shadow_promoted | 27 | y | — | — | — | — |
| GKOS | Medical Device Mean-Reversion & Rotation Recover | Fadin | 0.31 | 13 | Healthcare | 2026-08-17 | assignment_llm | 15 | y | — | — | — | y |
| BLZE | Network Security & Zero-Trust Edge | Mains | 0.30 | 17 | Technology | 2026-09-22 | merge:unlogged | 1 | y | — | — | y | — |
| XP | Wealth Management & Retail Brokerage Platforms | Mains | 0.07 | 12 | Financial Serv | 2026-09-01 | assignment_llm | 9 | y | — | — | y | y |
| HOOD | Wealth Management & Retail Brokerage Platforms | Mains | 0.31 | 12 | Financial Serv | 2026-08-21 | assignment_llm | 13 | y | — | — | y | y |

### Bridge to the 09-13 backtest's "95 of 504"

- Those 95 were ASSIGNMENT-NIGHT pairs judged against the PRIOR night's basket. Parsed from the committed doc: 95 rows = 90 distinct pairs; **23 of 90 distinct pairs are memberships on today's board** (25 rows; the rest left the board or the theme retired); of those 23 pairs, 16 still read below 0.35 today, 3 now read above it, 4 unjudgeable today (the table lists rows, so HOOD and TRAX appear twice).

| stock | theme (09-13 doc) | 09-13 reading | today |
|---|---|---|---|
| CHKP | Network Security & Zero-Trust Edge | 0.27 | 0.46 admit |
| CVLT | Network Security & Zero-Trust Edge | 0.31 | 0.50 admit |
| IVZ | Wealth Management & Retail Brokerage Platforms | 0.25 | 0.63 admit |
| ACA | Industrial Construction Execution & On-Site Supply | 0.18 | -0.16 reject |
| AGX | Industrial Construction Execution & On-Site Supply | 0.09 | 0.20 reject |
| CDNA | AI-Driven Diagnostics & Imaging Re-Rating | 0.14 | 0.15 reject |
| DGX | AI-Driven Diagnostics & Imaging Re-Rating | 0.27 | 0.28 reject |
| GKOS | Medical Device Mean-Reversion & Rotation Recovery | 0.29 | 0.31 reject |
| HOOD | Wealth Management & Retail Brokerage Platforms | -0.01 | 0.31 reject |
| HOOD | Wealth Management & Retail Brokerage Platforms | 0.01 | 0.31 reject |
| KBR | Industrial Construction Execution & On-Site Supply | 0.10 | 0.12 reject |
| LH | AI-Driven Diagnostics & Imaging Re-Rating | 0.22 | 0.29 reject |
| MSFT | AI-Powered Enterprise Analytics & Intelligent Work | 0.30 | 0.19 reject |
| NTNX | Enterprise Server, Storage & Data Infrastructure H | 0.06 | -0.19 reject |
| ORCL | AI-Powered Enterprise Analytics & Intelligent Work | 0.04 | -0.14 reject |
| QURE | Genetic Medicine: Gene Editing & Gene Therapy Inno | 0.23 | 0.29 reject |
| TBBB | Defensive Consumer Staples Rotation | 0.33 | 0.19 reject |
| TRAX | Inflammatory Disease & Immunology Biologics | 0.21 | 0.22 reject |
| TRAX | Inflammatory Disease & Immunology Biologics | 0.15 | 0.22 reject |
| TTEK | Industrial Construction Execution & On-Site Supply | 0.19 | -0.12 reject |
| XP | Wealth Management & Retail Brokerage Platforms | 0.26 | 0.07 reject |
| BOX | Enterprise Unstructured Data Storage Infrastructur | -0.17 | n/a unjudgeable:thin_basket |
| CORT | Peptide & Hormone Therapies for Metabolic & Endocr | 0.25 | n/a unjudgeable:thin_basket |
| MMED | Diabetes Management Devices (CGM, Insulin Pumps &  | 0.32 | n/a unjudgeable:thin_basket |
| PRCH | Digital Insurance Distribution & InsurTech Platfor | 0.05 | n/a unjudgeable:thin_basket |

### HOOD — the "partially correct" case, today's readings (descriptive; 0.35 is a per-pair bar, not best-of-many)

| theme | stage | HOOD is a member | reading | tape |
|---|---|---|---|---|
| Bitcoin Balance Sheet Proxies | Nascent | no | 0.74 | comoves |
| Bitcoin Holding & Trading Proxy Equities | Mainstream | no | 0.65 | comoves |
| Bitcoin Treasury & Crypto Proxy Equities Correlation Basket | Mainstream | no | 0.65 | comoves |
| Wealth Management & Retail Brokerage Platforms | Mainstream | yes | 0.31 | below_bar |
| Bitcoin Mining Stocks Rotation Reversal | Mainstream | no | 0.27 | below_bar |

## 3. What happened afterwards — OUT OF SAMPLE co-movement (not returns)

### W1 — the 09-13 backtest's board: board 2026-09-11 (119 themes, 718 memberships, 592 judgeable), in-sample = 60 sessions to 2026-09-11, out-of-sample = 9 returns 2026-09-14 … 2026-09-24

| group (in-sample verdict) | n | OOS judgeable | mean OOS co-movement | median | share < 0.35 OOS | share ≥ 0.35 OOS |
|---|---|---|---|---|---|---|
| would be EVICTED (in-sample < 0.35) | 60 | 58 | 0.30 | 0.36 | 29 of 58 (50%) | 29 of 58 (50%) |
| KEPT (in-sample ≥ 0.35) | 532 | 527 | 0.73 | 0.80 | 42 of 527 (8%) | 485 of 527 (92%) |

- Spearman rank correlation between the in-sample and out-of-sample readings over all 585 judgeable memberships: **0.67**.
- Noise floor: with 9 returns the standard error of a Pearson r near 0.3 is ≈ 0.34 — no per-name verdict is readable in this window; only the group contrast is.
- Price path, CONTEXT ONLY (not a verdict): median market-adjusted return over the window, evicted names -4.1% (n=58) vs their theme baskets -5.1% (n=58).

### W2 — engine-grade window: board 2026-08-12 (88 themes, 436 memberships, 338 judgeable), in-sample = 60 sessions to 2026-08-12, out-of-sample = 30 returns 2026-08-13 … 2026-09-24

| group (in-sample verdict) | n | OOS judgeable | mean OOS co-movement | median | share < 0.35 OOS | share ≥ 0.35 OOS |
|---|---|---|---|---|---|---|
| would be EVICTED (in-sample < 0.35) | 25 | 25 | 0.38 | 0.42 | 11 of 25 (44%) | 14 of 25 (56%) |
| KEPT (in-sample ≥ 0.35) | 313 | 307 | 0.73 | 0.78 | 24 of 307 (8%) | 283 of 307 (92%) |

- Spearman rank correlation between the in-sample and out-of-sample readings over all 332 judgeable memberships: **0.78**.
- Noise floor: with 30 returns the standard error of a Pearson r near 0.3 is ≈ 0.17 — a per-name direction is readable, with n.
- Price path, CONTEXT ONLY (not a verdict): median market-adjusted return over the window, evicted names -11.8% (n=25) vs their theme baskets -16.0% (n=25).

**Per name (readable at 30 returns): 11 of 25 would-be-evicted names kept failing to move with their theme (the tape was right); 14 of 25 started moving with it (the tape was early or wrong).**

| stock | theme | stage | in-sample | OOS (30 returns) | direction |
|---|---|---|---|---|---|
| CVLT | Network Security & Zero-Trust Edge | Mains | 0.33 | 0.83 | rose above the bar |
| FLS | Industrial Equipment & Flow Control – Capex Cycle  | Mains | 0.32 | 0.73 | rose above the bar |
| DPC | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.14 | 0.63 | rose above the bar |
| FSK | Private Equity & Alternative Asset Management Plat | Mains | 0.21 | 0.62 | rose above the bar |
| BFH | Consumer Fintech & Digital Credit Platforms | Fadin | 0.23 | 0.58 | rose above the bar |
| ROAD | Industrial Construction Execution & On-Site Supply | Accel | 0.28 | 0.57 | rose above the bar |
| EQPT | Industrial Equipment Rental & Material Handling | Accel | 0.32 | 0.54 | rose above the bar |
| TPC | Industrial Construction Execution & On-Site Supply | Accel | 0.22 | 0.52 | rose above the bar |
| INSM | Specialty Pharmaceutical Commercialization & Rare  | Mains | 0.30 | 0.51 | rose above the bar |
| MPWR | AI data center infrastructure buildout | Nasce | 0.29 | 0.51 | rose above the bar |
| CORT | Peptide & Hormone Therapies for Metabolic & Endocr | Mains | 0.21 | 0.50 | rose above the bar |
| AADX | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.12 | 0.47 | rose above the bar |
| ARXS | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.07 | 0.42 | rose above the bar |
| CMCO | Industrial Equipment Rental & Material Handling | Accel | 0.16 | 0.40 | rose above the bar |
| BLZE | AI data center infrastructure buildout | Nasce | 0.22 | 0.34 | still below |
| MRCY | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.28 | 0.34 | still below |
| CNMD | Medical Device Mean-Reversion & Rotation Recovery | Mains | 0.27 | 0.31 | still below |
| ATI | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.03 | 0.25 | still below |
| BMRN | Specialty Pharmaceutical Commercialization & Rare  | Mains | 0.24 | 0.23 | still below |
| RTX | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.12 | 0.21 | still below |
| DFNS | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.06 | 0.15 | still below |
| EMBJ | Defense Electronics & Aerospace Subsystem Supplier | Mains | 0.16 | 0.07 | still below |
| J | Industrial Construction Execution & On-Site Supply | Accel | -0.00 | 0.05 | still below |
| VLTO | Industrial Equipment & Flow Control – Capex Cycle  | Mains | 0.32 | -0.02 | still below |
| OMER | Specialty Pharmaceutical Commercialization & Rare  | Mains | 0.12 | -0.23 | still below |

- Mirror, the kept side: 24 of 307 (8%) in-sample-kept memberships read below 0.35 out of sample.

## 4. Tightness before / after, with the matched random-removal control

Tightness = mean leave-one-out co-movement of each member with the rest (no engine metric exists; the 09-13 doc's). Control = remove the SAME NUMBER of members at random from the theme's judgeable members, 300 draws, seed 20260925. 'control ≥ real' = draws whose after-tightness is at least the tape's.

### 4a. In-sample on today's board — a FLOOR by construction (removing the lowest-scoring members raises the mean of what is left)

| theme | stage | evicted | members | before | after | control mean | control ≥ real (of draws) |
|---|---|---|---|---|---|---|---|
| AI-Driven Diagnostics & Imaging Re-Rating | Mains | DGX, CDNA, HTFL, LH | 9 | 0.39 | 0.57 | 0.34 | 6/300 |
| AI-Powered Enterprise Analytics & Intelligent Wo | Fadin | MSFT, ORCL | 18 | 0.68 | 0.77 | 0.68 | 1/300 |
| Bank Stocks: Rising-Rate NIM Expansion | Fadin | BBVA, BCS, LYG, SAN, C, MFG, DB | 45 | 0.61 | 0.69 | 0.61 | 0/300 |
| Bitcoin Mining Stocks Rotation Reversal | Mains | IOND | 10 | 0.76 | 0.83 | 0.76 | 32/300 |
| Cloud Data Storage & Analytics Infrastructure | Mains | ESTC, APLD | 4 | 0.24 | n/a | n/a | n/a/0 |
| Commercial, Office & Home Furniture Retailers an | Fadin | ARHS | 5 | 0.49 | 0.54 | 0.47 | 64/300 |
| Crude & Product Tanker Shipping | Mains | SR, ATO | 13 | 0.76 | 0.87 | 0.76 | 5/300 |
| Defense Electronics & Aerospace Subsystem Suppli | Mains | EMBJ, RTX | 9 | 0.42 | 0.52 | 0.40 | 11/300 |
| Defense Intelligence & Cybersecurity IT Contract | Mains | EFOR, VVX | 7 | 0.52 | 0.65 | 0.49 | 17/300 |
| Defensive Consumer Staples Rotation | Fadin | TBBB, GO | 17 | 0.56 | 0.61 | 0.56 | 1/300 |
| Digital Advertising & Ad-Tech Monetization Platf | Mains | MGNI | 4 | 0.50 | n/a | n/a | n/a/0 |
| Diversified Power Generation Capacity Expansion  | Fadin | HNRG, AES, OGE, EVRG | 5 | 0.28 | n/a | n/a | n/a/0 |
| Energy Infrastructure & Services Complex | Fadin | FTK, WKC | 16 | 0.49 | 0.58 | 0.48 | 1/300 |
| Enterprise Server, Storage & Data Infrastructure | Nasce | NTNX | 8 | 0.50 | 0.60 | 0.50 | 49/300 |
| Fintech & Digital Finance Sector Re-rating on Fe | Fadin | XP, ITUB, PGY, KSPI, CHYM | 22 | 0.45 | 0.51 | 0.44 | 0/300 |
| Genetic Medicine: Gene Editing & Gene Therapy In | Fadin | QURE | 4 | 0.44 | n/a | n/a | n/a/0 |
| Global Agriculture Value Chain Recovery | Mains | AGRO | 4 | 0.56 | n/a | n/a | n/a/0 |
| Industrial Construction Execution & On-Site Supp | Fadin | TTEK, J, AGX, ACA, KBR | 8 | 0.17 | n/a | n/a | n/a/0 |
| Inflammatory Disease & Immunology Biologics | Fadin | AUPH, TRAX | 9 | 0.49 | 0.58 | 0.47 | 4/300 |
| Medical Device Mean-Reversion & Rotation Recover | Fadin | GKOS, INSP | 14 | 0.55 | 0.60 | 0.54 | 2/300 |
| Network Security & Zero-Trust Edge | Mains | BLZE | 18 | 0.71 | 0.74 | 0.71 | 22/300 |
| Wealth Management & Retail Brokerage Platforms | Mains | XP, HOOD | 13 | 0.42 | 0.49 | 0.41 | 6/300 |

- Across the 16 measurable changed themes: mean tightness **0.55 → 0.63**; random removal of the same count lands at **0.54** (n=16).

### 4b. OUT OF SAMPLE — evictions chosen on the in-sample window, tightness change read on the 9 OOS returns (W1, board 2026-09-11) — this is the reading that counts

| theme | stage | evicted | members | in-sample before → after | OOS before | OOS after | OOS control mean | control ≥ real (of draws) |
|---|---|---|---|---|---|---|---|---|
| AI-Driven Diagnostics & Imaging Re-Rating | Fadin | DGX, CDNA, HTFL, LH | 8 | 0.36 → 0.53 | 0.58 | 0.73 | 0.52 | 15/300 |
| AI-Powered Enterprise Analytics & Intelligen | Fadin | MSFT, ORCL | 16 | 0.69 → 0.77 | 0.80 | 0.88 | 0.80 | 22/300 |
| Commercial, Office & Home Furniture Retailer | Accel | ETD | 6 | 0.56 → 0.61 | 0.42 | 0.37 | 0.40 | 193/300 |
| Consumer Fintech & Digital Credit Platforms | Fadin | KSPI, PYPL | 14 | 0.45 → 0.48 | 0.54 | 0.56 | 0.53 | 71/300 |
| Defense Electronics & Aerospace Subsystem Su | Fadin | RTX, ARXS, EMBJ | 5 | 0.26 → n/a | 0.47 | n/a | n/a | n/a/0 |
| Defensive Consumer Staples Rotation | Fadin | UTZ, TBBB | 16 | 0.55 → 0.66 | 0.50 | 0.53 | 0.50 | 41/300 |
| Digital Insurance Distribution & InsurTech P | Fadin | GSHD, LIFE, PRCH, NP | 4 | 0.21 → n/a | 0.02 | n/a | n/a | n/a/0 |
| Diversified Power Generation Capacity Expans | Nasce | OGE, HNRG, KEP | 4 | 0.22 → n/a | 0.52 | n/a | n/a | n/a/0 |
| Energy Supply Disruption: Middle East Geopol | Mains | BTU, XPRO, FTK, NESR, WTTR | 59 | 0.71 → 0.77 | 0.73 | 0.78 | 0.73 | 1/300 |
| Enterprise Server, Storage & Data Infrastruc | Fadin | NTNX | 8 | 0.47 → 0.58 | 0.50 | 0.62 | 0.49 | 41/300 |
| Farm Economy Value Chain Re-Rating | Accel | FMC | 7 | 0.52 → 0.56 | 0.68 | 0.80 | 0.67 | 41/300 |
| Global Agriculture Value Chain Recovery | Mains | DOLE | 9 | 0.47 → 0.48 | 0.56 | 0.57 | 0.55 | 106/300 |
| Hospital & Behavioral Health Facility Proced | Fadin | ACHC | 5 | 0.45 → 0.63 | 0.59 | 0.62 | 0.57 | 128/300 |
| Industrial Construction Execution & On-Site  | Fadin | TPC, TTEK, J, ACA, KBR, FLR | 7 | 0.21 → n/a | 0.37 | n/a | n/a | n/a/0 |
| Industrial Equipment & Flow Control – Capex  | Fadin | FLS, VLTO | 4 | 0.36 → n/a | 0.31 | n/a | n/a | n/a/0 |
| Inflammatory Disease & Immunology Biologics | Fadin | TRAX | 13 | 0.49 → 0.54 | 0.67 | 0.65 | 0.67 | 235/300 |
| Legacy Telecom & Pay-TV/Broadcasting Distrib | Nasce | CHTR, TDS, ECHO | 4 | 0.23 → n/a | -0.12 | n/a | n/a | n/a/0 |
| Medical Device Mean-Reversion & Rotation Rec | Fadin | INSP | 14 | 0.58 → 0.61 | 0.64 | 0.68 | 0.64 | 40/300 |
| Molecular & Genomic Diagnostic Testing | Fadin | VCYT, CDNA, BLLN | 4 | 0.27 → n/a | 0.62 | n/a | n/a | n/a/0 |
| Neurology & Rare Disease CNS Biopharmaceutic | Nasce | BIIB, EWTX, ARWR | 5 | 0.36 → n/a | 0.41 | n/a | n/a | n/a/0 |
| Oil Refining & Marketing | Nasce | OGS, AESI, SWX, SR | 27 | 0.58 → 0.62 | 0.58 | 0.63 | 0.57 | 6/300 |
| Oncology Therapeutics RS Turnaround | Fadin | SMMT, INCY, ZLAB | 16 | 0.49 → 0.53 | 0.50 | 0.49 | 0.49 | 148/300 |
| Peptide & Hormone Therapies for Metabolic &  | Fadin | CRNX, CORT | 4 | 0.37 → n/a | n/a | n/a | n/a | n/a/0 |
| Wealth Management & Retail Brokerage Platfor | Fadin | XP, APAM | 20 | 0.48 → 0.51 | 0.50 | 0.55 | 0.50 | 16/300 |

- W1: across the 15 measurable changed themes, OOS tightness 0.59 → 0.63 (tighter in 12 of 15); random removal of the same count lands at 0.58; the tape's eviction beats the random control's mean in 12 of 15 themes, and beats ≥95% of draws in 3 of 15.

### 4b. OUT OF SAMPLE — evictions chosen on the in-sample window, tightness change read on the 30 OOS returns (W2, board 2026-08-12) — this is the reading that counts

| theme | stage | evicted | members | in-sample before → after | OOS before | OOS after | OOS control mean | control ≥ real (of draws) |
|---|---|---|---|---|---|---|---|---|
| AI data center infrastructure buildout | Nasce | BLZE, MPWR | 8 | 0.56 → 0.67 | 0.58 | 0.62 | 0.55 | 31/300 |
| Consumer Fintech & Digital Credit Platforms | Fadin | BFH | 7 | 0.51 → 0.55 | 0.58 | 0.56 | 0.57 | 137/300 |
| Defense Electronics & Aerospace Subsystem Su | Mains | DFNS, MRCY, DPC, EMBJ, AADX, ARXS, ATI,  | 9 | 0.15 → n/a | 0.31 | n/a | n/a | n/a/0 |
| Industrial Construction Execution & On-Site  | Accel | J, ROAD, TPC | 4 | 0.23 → n/a | 0.34 | n/a | n/a | n/a/0 |
| Industrial Equipment & Flow Control – Capex  | Mains | FLS, VLTO | 10 | 0.59 → 0.65 | 0.61 | 0.67 | 0.60 | 44/300 |
| Industrial Equipment Rental & Material Handl | Accel | CMCO, EQPT | 4 | 0.35 → n/a | 0.47 | n/a | n/a | n/a/0 |
| Medical Device Mean-Reversion & Rotation Rec | Mains | CNMD | 4 | 0.40 → n/a | 0.23 | n/a | n/a | n/a/0 |
| Network Security & Zero-Trust Edge | Mains | CVLT | 13 | 0.63 → 0.66 | 0.81 | 0.81 | 0.81 | 81/300 |
| Peptide & Hormone Therapies for Metabolic &  | Mains | CORT | 5 | 0.42 → 0.46 | 0.29 | n/a | n/a | n/a/0 |
| Private Equity & Alternative Asset Managemen | Mains | FSK | 11 | 0.68 → 0.73 | 0.75 | 0.76 | 0.75 | 50/300 |
| Specialty Pharmaceutical Commercialization & | Mains | OMER, INSM, BMRN | 10 | 0.42 → 0.52 | 0.30 | 0.35 | 0.27 | 66/300 |

- W2: across the 6 measurable changed themes, OOS tightness 0.60 → 0.63 (tighter in 4 of 6); random removal of the same count lands at 0.59; the tape's eviction beats the random control's mean in 4 of 6 themes, and beats ≥95% of draws in 0 of 6.
