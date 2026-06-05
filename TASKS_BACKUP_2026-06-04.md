# Apollo #-task tracker — backup snapshot (2026-06-04)

**Why this file exists:** during a *continued* session on 2026-06-04 the task tool
detached from the persistent store (TaskCreate restarted at #1; #38–#195 became
unreachable via TaskList). The tasks were NOT deleted — they appeared in every
system-reminder this session. This is a hard backup transcribed from those
reminders in case a restart doesn't reload them. Statuses are as of 2026-06-04.

**To restore:** if a fresh session's TaskList shows #38–#195, ignore this file.
If it shows only #1–#2, recreate the open ones below (completed ones don't need
recreating). `BACKLOG.md` is the human cross-view and remains the SoT for projects.

---

## Open tasks (pending / in_progress) — the ones that matter

| # | status | subject |
|---|---|---|
| 55 | pending | Revenue-stage threshold re-check at 30-60 day cohort intervals |
| 56 | pending | Rubric Axis 2 distortion from corporate-action EPS in prior-year quarter (spinoffs/M&A) |
| 60 | pending | 9M Day 2 cohort growth tracking + ATR-gate re-evaluation at N≥30 entered |
| 65 | pending | 9M Day 2 methodology alignment review (architectural — filed 5/21) |
| 81 | pending | Day 2 OPG vs ORB routing — 4% gap threshold per Pradeep |
| 97 | pending | Entry-technique detector: Low-volume rest (tight-range #4) |
| 113 | pending | duplicate_scan locks in FIRST tier — should later same-day conditions trigger rescore? |
| 115 | pending | Refactor 3-detector boilerplate (post-Tuesday first-fire validation) |
| 116 | pending | Hot-path efficiency: snapshot cache + universe cache for 3 intraday detectors |
| 121 | pending | Switch briefing parse_mode from legacy Markdown to MarkdownV2 or HTML |
| 134 | pending | Flag-break detector: borderline-trigger floor (#94 followup) |
| 146 | pending | Flag state machine: TIGHTENING→TRIGGERED on direct range break (Fix A investigation) |
| 149 | pending | Missing-data root cause investigation — fix upstream, not safety-net carve-outs |
| 150 | in_progress | (DOWNGRADED 6/3) entry stop-limit run-through — fill-rate/opportunity-cost, gated entry-tuning |
| 151 | in_progress | P0 — Partial-exit hardening: architectural split + preflight G6 + outcome-history circuit breaker (FPS recurred 6/4 — see mi_audit_log) |
| 152 | pending | News-source-quality drift detector — direction-aware alerting (#112-class) |
| 165 | pending | Theme-discovery $10 price-floor excludes sub-$10 momentum leaders (gate #5, APPS) |
| 166 | pending | Verify #98 U&R first scan tick (Mon 2026-06-01 ~9:35 AM ET) |
| 167 | in_progress | Stocks in Play project — kickoff session (categorize / prioritize / map + WS breakdown) |
| 168 | pending | Stocks-in-Play WS-C: actionability/quality filter for entry-technique alerts |
| 170 | in_progress | EP cooldown → extension/structure-aware re-setup admission |
| 172 | pending | Post-validation /simplify refactor of partial-exit hardening (deferred 2026-06-01) |
| 176 | pending | Automated SoT/roster drift-check (scheduled ping — the no-prompt guarantee) |
| 178 | pending | Merge /why into /setup via optional date-arg (observability UX) |
| 179 | pending | Write-side root fix: mi_orb_extension_shadow.state double-encoding (#177 band-aid → root) |
| 180 | in_progress | Unify would-have-filled sims into one EOD pass (complete bars) — gap_through under-count fix |
| 181 | in_progress | Retire PDT-lockout safeguard + /status PDT display (Alpaca Rule 4210, eff. June 4 2026) |
| 182 | pending | Verify paper cohort isn't under-filling entries vs live (IEX feed misses SIP crosses) |
| 183 | in_progress | ORB cancellation classifier mislabels SIP fills as clean_miss (reads IEX / wrong window) |
| 184 | in_progress | Broker-authoritative trade-state mirror — DB must reflect Alpaca SoT at all times (cutover prereq) |
| 185 | pending | Apollo Trades dash: surface corrupt-stop exclusion count (CRMD silent-swallow) |
| 186 | pending | gemini_validation col=Perplexity (misnomer) + EVALUATE reviving Gemini as a 3rd validator |
| 187 | in_progress | Catalyst SOURCING gap — ingest SEC 8-K/EDGAR for gappers (RUM $270M deal missed by BOTH LLMs) |
| 188 | pending | Model eval + tune — NEAR-TERM: Haiku catalyst-grade quality/cost vs Sonnet, then institutionalize quarterly |
| 189 | in_progress | Catalyst MATERIALITY judgment — news existence ≠ EP-grade (LLM + rules) |
| 190 | in_progress | Track A — catalyst grade re-arch: grade the GROUNDED summary on Sonnet (async shadow → promote) |
| 191 | pending | Universe pre-filter — catalyst-source-signal gate (cost+quality twofer) |
| 192 | pending | Post-bake /simplify deferrals from 6/4 (leading-ZWSP gate gap + grade-path DRY) |
| 194 | pending | Apollo Themes: daily auto-export of theme snapshot → portfolio-app2 (freshness fast-follow) |
| 195 | in_progress | SECURITY: portfolio-app2 PUBLIC repo had .streamlit/secrets.toml committed — rotate app_password + Anthropic key |

### Dash follow-ups created this session (live in portfolio-app2/CLAUDE.md too)
| # | status | subject |
|---|---|---|
| (session #1) | pending | portfolio-app2: consolidate duplicated C_DARK/C_LIGHT palette (Portfolio + Apollo Trades) — /simplify deferral |
| (session #2) | pending | portfolio-app2: custom content lags the native theme switch (repaints on next interaction) |

---

## Completed tasks (for the record — no need to recreate)

#38 #39 #40 #41 #42 #43 #44 #45 #46 #47 #48 #49 #50 #51 #52 #53 #54 #57 #58 #59
#61 #62 #63 #64 #66 #67 #68 #69 #70 #71 #72 #73 #74 #75 #76 #77 #78 #79 #80
#82 #83 #84 #85 #86 #87 #88 #89 #90 #91 #92 #93 #94 #95 #96 #98 #99 #100
#101 #102 #103 #104 #105 #106 #107 #108 #109 #110 #111 #112 #114 #117 #118 #119 #120
#122 #123 #124 #125 #126 #127 #128 #129 #130 #131 #132 #133 #135 #136 #137 #138 #139 #140
#141 #142 #143 #144 #145 #147 #148 #153 #154 #155 #156 #157 #158 #159 #160 #161 #162 #163 #164
#169 #171 #173 #174 #175 #177
#193 (Apollo Themes tab — built + deployed + working via native theme; effectively done this session)

(Full subjects for the completed set are in this session's transcript + git history;
they're done, so only the open list above needs to survive.)
