# Weekend scope — 2026-05-15 Fri → 2026-05-18 Mon pre-open

Plan committed at start of weekend so we can review delta on Monday. Update
status in-line as items complete; final retrospective at end.

## Context

Two trade-state corruption bugs in 36 hours (CRMD AmbiguousParameter 2026-05-14,
KLAR/ARM stop-clobber 2026-05-15). Same architectural fault each time: multiple
writers to trade state, no ownership rule, last-write-wins by accident. Five
incidents this week. The boot-time prepare validation (Gate 5 B) catches type
errors but not semantic-overwrite. Live cutover composite (5/22 target) thinks
it's safer than it is.

Friday 10am PT — market closes 1pm PT — no trading next 3 days (weekend) — this
is the proper window for architectural hardening.

## Tracks (1=highest priority)

### TRACK 1 — Live-cutover architectural hardening
Addresses recurring "DB tracks attempt not outcome" + "multi-writer no
ownership" class. Foundation for live-$ readiness.

### TRACK 2 — EP Selectivity Phase 1
User-committed Fri/weekend window. ~50 variables across §A-§G, 5/14 case
studies (ONDS/CPA/KLAR/CSCO) + 9-name missed-winners cohort
(OSS/STRL/FTNT/TWLO/BAND/MXL/HIMX/INOD/DDOG).

### TRACK 3 — Loose-end cleanup
Small items batched on Friday afternoon.

### TRACK 4 — Methodology damage assessment
Quantify 2026-05-07 → 2026-05-15 corruption window impact on Gate 3
R-expectancy.

### TRACK 5 — Strategy explorer runs (opportunistic)
Only if Sunday finishes early.

---

## Friday afternoon (today) — small-batch session

**Track 1 prep**:
- [ ] Audit all 40+ `mi_live_trades` write sites; build column→writer matrix
- [ ] Draft `docs/architecture/trade-state-ownership.md` — per-column authorized writers + exceptions + violation list
- [ ] GOOGL #56 audit log spot-check (data gathering for Sunday)

**Track 4 (methodology damage)**:
- [ ] Pre/post reconcile cohort R numbers for ARM #107 + KLAR #149
- [ ] Add corruption-window note to `paper_r_expectancy_validation` YAML

**Track 3 quick wins**:
- [ ] Pass1 protect-strip equal-size test fixture
- [ ] Perplexity sanitizer test fixture
- [ ] `format_trade_attempts` live-path verify
- [ ] Gate 5 tomorrow verifications (BW partial confirmed today, AIXI RS, SNDK theme stick, 9M intraday M&A first firing)
- [ ] `BACKLOG.md` status sync (P13, P26, P27 → done)

## Saturday — Track 2 EP Selectivity Phase 1 (focused)

Single end-to-end day. Output: `docs/decisions/0003-ep-selectivity-overhaul.md`.

- [ ] **P1.1** Master cohort SQL — join `mi_ep_alerts × scan_log × live_trades × scan_outcomes × orb_shadow_trades × missed_outcomes × themes × flag_candidates × daily_closes`, ~60d window
- [ ] **P1.2** Per-dimension outcome breakdowns — every variable × win rate / R
- [ ] **P1.6** Class A/B/C split — 5/14 cases as fixtures
- [ ] **P1.7** EP detector latency investigation (CPA-class late fires)
- [ ] **P1.3** D1-D6 new-dimension prototypes (D1 fundamentals magnitude = highest impact)
- [ ] **P1.4** Catalyst-prose labeled training set (~400-500 alerts; operator labels in parallel)
- [ ] **P1.5** Score-weight regression — `forward_5d_R ~ existing scoring components`
- [ ] Produce ADR doc

## Sunday — Track 1 main work (focused)

Single end-to-end day. Output: refactored write sites + Gate 5 G shipped.

- [ ] Refactor stop_price/hard_stop/entry_price/total_pnl/remaining_shares/partial_taken write sites per ownership doc
- [ ] Ship **Gate 5 G** — `scripts/audit_column_writes.py` static-analysis check + `[5c/5] column-write authority` deploy.sh step
- [ ] GOOGL #56 deep investigation — was 5/05 09:35 stop_update contaminated?
- [ ] If GOOGL contaminated: file as third reconcile
- [ ] Update `docs/incidents/2026-05-14-crmd-naked-position.md` §6 to add Gate 5 G
- [ ] Update `live_cutover_decision` review to add Gate 5 G
- [ ] Final deploy + both preflights green
- [ ] Synthetic test: insert fake column-write violation, confirm preflight blocks

## Monday pre-open — verification only

- [ ] Stuck-fill watchdog running every minute during market hours
- [ ] BW partial fill state correct (`partial_taken=TRUE`, exits populated)
- [ ] All reconciles holding
- [ ] Both preflights green on first run

**No new code Monday morning.**

---

## Bumped to opportunistic (only if Sunday finishes early)

- TI3 fishhook_v3_explorer run
- TI5 ep_shape_explorer run
- TI4 yfinance coverage spike run
- P25 Theme Rank Evolution Dashboard local exploration

---

## Schedule density

| Day | Mode | Items | Budget |
|---|---|---|---|
| Fri PM | Mixed small | 8-10 items + doc | ~5-6 hr |
| Saturday | Focused analysis | EP Selectivity Phase 1 end-to-end | ~10-14 hr |
| Sunday | Focused refactor | Track 1 + Gate 5 G + GOOGL + verify | ~8-10 hr |
| Monday pre-open | Verify only | Watch + confirm | ~1 hr |

## Commit cadence

- Friday: 2-3 commits (small batch + ownership doc)
- Saturday: 1 commit (ADR + supporting analysis scripts) — NO production code Saturday
- Sunday: 4-6 commits (each refactor + Gate 5 G + GOOGL + post-mortem)

## What gets dropped if behind

- Drop Track 5 entirely (strategy explorers)
- Drop Track 3.4 verify (format_trade_attempts already known working)
- Track 2 scope-cut: drop P1.3 D5+D6 if D1+D2 alone shows strong signal
- **NEVER drop**: Track 1 (architectural fix), Track 4 (damage assessment)

## Risk flags

- Track 1 refactor touches hot code — every change needs preflight + paper-mode synthetic test before commit
- Track 2 P1.4 catalyst-prose labeling needs operator (user) — solo blocker if I rush ahead without labels
- GOOGL investigation might surface 3rd compound corruption → Track 1 scope expands

## Hard deadlines

- **Sunday 8am ET**: weekly system review fires. Output should reflect post-reconcile state. Track 4 must complete before.
- **Sunday evening**: final deploy + preflight. No new code Monday morning.
- **Monday 9:30 ET market open**: all changes verified, stuck-fill watchdog running, BW partial sell fills correctly.

## Monday retrospective (fill in)

- What landed
- What slipped
- What surprised
- Next-week implications
