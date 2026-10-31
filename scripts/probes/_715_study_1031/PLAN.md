# #715 — EP entry for names that qualify AFTER the open: pre-registered study plan (2026-10-31)

**Question (his catch, REGN 2026-10-30):** a name admitted on the real-time flip-up — the opening gap
BELOW the 9% floor, the live price over it minutes later — is bought at the 09:30 bar's high, which sits
below the floor that admitted it. The #500 chase cap (1.5× the planned risk, planned = ORB high − stop)
then refuses the price that actually qualified it. REGN: ORB high $869.88, stop $817.50 (= 2 × $843.69 −
$869.88), planned risk $52.38/sh → the cap allowed a buy up to **$896.07**; the floor price was **$892.46**
(= $818.77 × 1.09); the live price at submit was $926.48 (limit $928.33, risk $110.83/sh = 2.12× planned)
→ `setup:chase_cap_exceeded`, no order.

**What this study is:** a $0 replay of the 51 flip-ups that became HIGH since 2026-08-02, from STORED
minute and daily bars, under the CURRENT entry and exit rules, comparing today's anchor against three
alternatives. **What it is not:** a rule change. Entry discipline is THE LINE — the deliverable is one
table and a rec; nothing moves without his sign-off, and a change goes through CHANGE_PROCESS (N ≥ 10).

**Everything in §1–§6 is written BEFORE any outcome bar is read.** The capture files were written and
parsed on 2026-10-31 (Sat) before the prod pull; the stage-2 script is written against this plan and
run once.

---

## 0. Files and run order

| step | file | what | status |
|---|---|---|---|
| 1 | `capture/c1_population.sql` → `c1_population.out` | the population, fates, inputs, toggles, coverage | written 10-31, parsed (pglast 8.7, 17 statements), **not yet run** |
| 2 | `capture/c2_bars.sql` → `c2_bars.out` | 1-min bars 09:30–16:00 ET for the 51 ticker-days + daily rows 2026-06-01..today for their tickers | written 10-31, parsed (4 statements), **not yet run**; the `.out` (~26k rows) is not committed — no gitignore rule covers probe `.out` files today, add it at commit time; `c1_population.out` (a few hundred rows) IS committed as the capture-once artefact |
| 3 | `s2_replay.py` → `s2_replay_out.txt`, `s2_rows.tsv` | stage 2: composition → calibration → four options → the table | to write after the capture lands, per §2–§6 |

Both captures: `SET default_transaction_read_only = on`, `\set ON_ERROR_STOP off` (a failing section
prints its error and the rest still lands), `\pset footer off`, `\echo === SECTION ===` headers, `|`
separated (the main loop runs `psql -A -F '|'`); text columns have `|` → `¦` and newlines → spaces.
Run from the laptop, once each (the exact commands are in each file's header):

```
ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" \
  < scripts/probes/_715_study_1031/capture/c1_population.sql > scripts/probes/_715_study_1031/capture/c1_population.out
ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" \
  < scripts/probes/_715_study_1031/capture/c2_bars.sql       > scripts/probes/_715_study_1031/capture/c2_bars.out
```

Stage 2 reads the two `.out` files and NOTHING else (no DB, no network, no re-pull). It reads the
sections with the same header/`|` convention `scripts/probes/_wk1010_559/readcap.py` reads (tab there, pipe
here); lines before the first `=== ` header (`SET`, `Default footer is off.`) and any stray psql notice are
skipped, never parsed as rows. Columns were checked against `agents/market_intelligence/db.py`
CREATE/ALTER blocks — none guessed.

---

## 1. Population — stated first, before any outcome

**Definition (reused VERBATIM from `scripts/probes/_regn_1030/q3_flipups.sql`):** the distinct
(ET date, ticker) pairs of `mi_audit_log` rows with `event_type = 'ep_rt_floor_flip_up'` and
`created_at >= '2026-08-02'`, ticker = the summary's leading token, joined to a `mi_ep_alerts` row with
`score_tier = 'HIGH'` on the same `alert_date`. On 2026-10-30 that read **871 flip-ups → 51 became HIGH →
10 filled, 3 chase-cap skips**. `c1 === POPCOUNT ===` re-runs q3's own statement; `=== CHECKS ===` prints
the row count. Stage 2 asserts 51 and names any delta (the only legitimate delta is a flip-up on a session
after 10-30; there is none — the capture runs on Saturday 10-31).

**Composition table (stage 2's first output, no outcome column):**

| split | why it must be shown, not pooled |
|---|---|
| admission era: flip-up tick before vs on/after **2026-08-27** (`rule_eras.ADMISSION_SWITCHES` `rubric_v4_rt_gap_authority`, first acting session 08-28) | before 08-27 the real-time gap was NOT authoritative — a pre-08-27 "flip-up that became HIGH" was admitted by the delayed read crossing later, not by the flip. Same geometry, different admission mechanism. Reported as a column; the headline table is the post-08-27 cohort, the pre-08-27 rows are a second row. |
| floor on the day: **10%** (before 08-19) vs **9%** | parsed from the flip-up summary (`≥9` / `≥10`), never hard-coded. **Fallback, fixed now:** if `floor_pct_from_summary` is NULL on a row (format drift, or a non-UTF8 `client_encoding` in `RUN` mangling `≥`), the date rule from `rule_eras.ADMISSION_SWITCHES` applies — `gap_floor_9`, first acting session 2026-08-20: alert day ≥ 08-20 → 9%, else 10% — and the row is flagged `floor_from_date`. |
| geometry: ORB high (09:30 bar high) **≥ floor price** vs **< floor price** | the "buy point below the floor" problem exists only in the second class; in the first, (a) and (c) are identical to today by construction. |
| opening gap (09:30 bar open vs prev close) ≥ floor vs below | (b)'s admit set. |
| first crossing minute: 09:30 bar, 09:31–09:44, ≥ 09:45 (window shut), never (bars only — the live read saw a print the bars don't) | a crossing at/after 09:45 cannot be entered under ANY option (the ORB window is common to all four). |
| stored fate today: filled / chase-cap skip / out-of-window / gap-below-floor / other skip / blocked / no trade row | the calibration target (§4). |
| minute-bar coverage: has the 09:30 bar; bars in 09:30–10:00 (of 30); RTH bars (of 390) | a ticker-day without its 09:30 bar has no ORB and is reported `no_orb_bar`, never walked. |

**Floor price** = `prev_close × (1 + floor/100)`, prev close = the latest `mi_daily_closes` row strictly
before the day with `close > 0` — `db.get_prev_close`'s exact rule, which is the detector's denominator
(c1 `POP.prev_close`). `mi_ep_scan_log.prev_close` for the same ticker-day is captured as a cross-check;
a mismatch > 0.5% is reported per row and the detector's own `prev_close` (scan log) wins for that row
because it is what the live floor used.

**Sizing frame.** Live shares = `risk_dollars / (anchor − stop)` (`order_manager`: `risk_per_share =
orb_high − stop_loss_price`). So one share-count unit of risk = the PLANNED per-share risk, and every
option's dollars compare at equal budget in **budget-R** = `pnl_per_share / (anchor − stop)`. A fill above
the anchor (the #500 limit path) carries more than one budget-R on a full stop-out — that is the chase
cap's whole subject, so the worst loss is reported in budget-R, where it can read below −1.0.

---

## 2. The rules replayed — precisely

### 2.1 Common mechanics (identical across today and (a)/(b)/(c); only the anchor / admit / cap differ)

Sources: `docs/setups/magna53_ep.md` (ORB window, #500, gap re-check), `docs/setups/exit_discipline.md`
(the depth exit live since 2026-10-12, first acting session 10-13), `broker/order_manager.py`
(`_pick_entry`, `_chase_cap_reason`, `CHASE_RISK_INFLATION_CAP = 1.5`, `stop_loss_price = 2·orb_low −
orb_high`, `stop_limit_buy_price`), `broker/entry_pipeline.py` (`check_rt_gap_floor`),
`backtester/filters.py` (`validate_orb_entry`, `compute_atr_14`), `scheduler.py:1247` (the window).

1. **ORB bar** = the stored 09:30 ET 1-minute bar (`mi_intraday_bars`). The live pipeline serves only a
   sanity-checked true 09:30 bar; c1 `EVENTS.orb_bar_fetched` cross-checks O/H/L on every ticker-day that
   reached the fetch (§4 check 3).
2. **Window.** An alert whose ORB entry can start at 09:31:00–09:44:59 ET is in the window; a HIGH first
   graded at/after 09:45 is `WINDOW_OUT_OF_ORB` → no entry, under every option. **Submit second**, in this
   order: the ticker-day's first `orb_bar_fetched` audit row's timestamp (it IS the submit moment — REGN
   09:36:30.198, the cap skip 80 ms later); else its first `orb_triggered` row; else the alert's
   `detected_at`. **Submit minute** = the later of 09:31 and the minute AFTER the submit second's minute
   (the first bar that is certainly after the submit second is the next one). Pre-open HIGHs (detected
   before 09:30) submit at 09:31 off the stream's 09:30 bar close. The floor the submit-time re-check
   uses (`rt_gap_floor_pct`, passed by the MAGNA53 caller of `submit_trade_entry`) is confirmed from the
   call site at stage 2 and recorded in `s2_replay_out.txt`; this plan assumes it equals the scan floor.
3. **Latest-trade proxy at submit** = the OPEN of the submit-minute bar (primary). Sensitivity: the CLOSE
   of the alert-minute bar. Calibrated on the rows where the live latest is stored (§4 check 1): a #500
   limit entry's `mi_live_orders.limit_price / 1.002`, and a chase-cap skip's `limit $X` in its
   `skip_reason` (REGN: $928.33 / 1.002 = $926.48).
4. **Submit-time gap re-check** (`ep_rt_entry_gap_recheck`, ON since 2026-08-02, c1 `TOGGLES` confirms):
   skip `setup:gap_below_floor` when `proxy < floor price`. Common to all options.
5. **Entry gates on the anchor bar** (`validate_orb_entry`): zero range → `setup:zero_range`; range >
   1.5 × ATR14 → `setup:stop_too_wide`. ATR14 = Wilder TR mean over the last 14 TRs from daily rows with
   `trade_date < alert day` (the live 09:31 path has no same-day bar; ≥ 10 rows else no gate), from
   `c2 DAILY`. `mi_live_trades.atr_14` on rows that reached sizing is the cross-check.
6. **Entry order.** If `proxy ≤ anchor high`: a stop-limit buy, stop = anchor high, limit =
   `max(high × 1.005, high + 0.02)` rounded to cents, walked over the minute bars from the submit minute
   through 09:59 by `broker/hour_bar_walk.entry_walk` (mirrors `sustain_reject_replay.entry_walk`: fill at
   the level on the first bar whose high reaches it; at the open if the bar opens in [level, limit]; the
   limit arms above it; `no_entry` on a fully covered window; abstain on gaps). If `proxy > anchor high`:
   the #500 **limit fallback**, limit = `round(proxy × 1.002, 2)`, **chase cap**: refused when
   `limit − stop > 1.5 × (planned)`, `planned` per option (§2.2); else filled AT THE LIMIT on the first bar
   from the submit minute whose low ≤ limit, before 10:00; never → cancelled.
7. **10:00 cancel.** Anything unfilled at 10:00 ET is cancelled → `no_entry`.
8. **Placed stop** = `2 × anchor_low − anchor_high` (= fill − 2R only when the fill is at the anchor;
   the stop is set from the anchor, as live). **R frame for the harvest ladder** = `fill − anchor_low`
   (`order_manager.profit_target_r_per_share`'s ORB frame): partial 1/3 at `fill + 8 × R`, price-armed
   breakeven at `fill + 3 × R` (`mi_strategies.profit_trigger_r / breakeven_arm_r`, c1 `STRATEGIES`
   confirms 8 / 3).
9. **Exit** = the CURRENT rule, §3.
10. First attempts only (`entry_attempt = 1`); re-entries after a stop are out of scope.

### 2.2 The four rules

| | anchor (buy = high, stop = 2·low − high) | admit | chase-cap `planned` |
|---|---|---|---|
| **today** | the 09:30 bar | every one of the 51 | `orb_high − stop` |
| **(a) crossing-bar anchor** | the FIRST RTH 1-min bar (from 09:30) whose **HIGH ≥ floor price** — "the bar where it crossed the floor"; sensitivity: first bar whose CLOSE ≥ floor | every one of the 51 whose crossing bar closes before 09:45 and whose submit minute (§2.1.2) is in the window | `crossing_high − stop_a` |
| **(b) opening gap must clear the floor** | the 09:30 bar (today's) | only names whose **09:30 bar OPEN ≥ floor price** (official open; `mi_daily_closes.open_price` cross-checks) | today's |
| **(c) cap measured from the floor** | the 09:30 bar (today's) | every one of the 51 | `max(orb_high, floor price) − stop` — sizing UNCHANGED (still on `orb_high − stop`, as the PLAN line states it) |

Notes fixed in advance:
- (a) when the crossing bar IS the 09:30 bar, (a) ≡ today. The crossing bar's own range feeds the
  zero-range / stop-too-wide gates and the stop: a 1-minute crossing bar can be far narrower than the
  ORB, so R shrinks, size grows, and the cap tightens — the cap test uses the crossing-bar geometry.
  If the proxy at submit is above the crossing high, the #500 path applies with that geometry. So (a)
  can skip a name today enters; that is a result, not a defect.
- (b) is a pure subset of today: its entries are today's entries minus the names it refuses. Its table
  row IS today's row on the subset; the second number that matters is what it REMOVES.
- (c) REGN worked: floor $892.46 > ORB high $869.88 → `planned_c` = $892.46 − $817.50 = $74.96 → the cap
  allows a limit up to $929.94 → the $928.33 limit is admitted, risk $110.83/sh on shares sized for
  $52.38/sh → a full stop-out costs **2.12 budget-R**. That is the cost (c) buys its entries with; the
  table shows it in the worst-loss column. A variant **(c′) — size on the floor-based planned risk too**
  — is reported as a sensitivity row (its dollar risk stays ≤ 1.5 budget-R), not as a fourth option.
- Floor price per row = `prev_close × (1 + floor_pct/100)` with the DAY'S floor (10% / 9%, §1).

---

## 3. Outcome measure

### 3.1 PRIMARY — the CURRENT exit, walked by the existing harness (reused, not rebuilt)

**Reused:** `agents/market_intelligence/live_fill_counterfactuals.walk_arm(...)` with `depth_exit=True` —
the #482 recorder's own walker, which since 2026-10-11 (#687) walks the depth exit a row stamped
`exit_rule='depth'` runs, calling the SAME pure functions the 16:45 job calls
(`exit_logic.depth_stop_price`, `exit_logic.adr20_pct_from_bars`; parity pinned by
`tests/test_depth_era_replays.py`). Stage 2 calls it exactly as the recorder's `live_replay` arm does on a
depth row (`live_fill_counterfactuals.py:1240-1257`):

```
walk_arm(entry=fill, stop=placed_stop, target=fill + 8·(fill − anchor_low),
         day0_bars=<fill day 09:30-16:00 minutes>, fill_idx=<fill minute>,
         sessions=<(date, daily bar) for the ≤40 sessions after the fill day, through the last settled session>,
         prior_closes=<closes in the 40 calendar days before the alert>,
         harvest="live_ladder", fill_day=d, breakeven_at_partial=True, trail_prior_closes=True,
         ladder_partial=False, horizon=40, breakeven_at_r=3.0, r_frame_ps=fill − anchor_low,
         trail_mode="sma", depth_exit=True,
         depth_adr20_pct=exit_logic.adr20_pct_from_bars(<≤20 daily bars before the alert>))
```

Day 0 is the minute walk (stop-first, same-bar ambiguity → abstain, never guessed); from session 1 the
resting stop is `depth_stop_price` (one ADR20 under the max(SMA10, SMA20) line, raise-only); a close below
the line sells at the NEXT open. The last settled session is read from c1 `SESSIONS` (Fri 2026-10-30 if
its daily rows are stored). Module import offline follows
`scripts/probes/_wk1011_depth_era/before_after_replay.py` (mocked DB; the walker is pure).

**Two horizons, both pre-registered, both run — the DECISION horizon is 20.** The recorder's
`HORIZON_SESSIONS = 40` (~8 weeks) can only settle alerts up to ~2026-09-03, so under it most of the 51
come back `horizon` (marked) and the §6 sample rule could never be met — a fact known before any data.
So stage 2 runs `walk_arm(..., horizon=20)` as the decision walk (the §5 table and every §6 threshold are
read at 20 sessions: an arm still open at session 20 is `horizon` with its mark), and the `horizon=40`
walk beside it, reported for the runners only (how much of the tail lives past session 20). Alerts
after ~2026-10-01 are still `horizon`/`pending` at 20; the table says how many.

**Why not `scripts/ep_replay.py` / `_wk1010_559/s2_replay.py`:** their `RULESETS["current"]` is era D —
the plain trail, pre-depth (`s2_replay.py` pins `LAST_SETTLED = 2026-10-09`, "the last settled session
before Monday's depth-exit go-live"). No ep_replay rule-set models the depth exit; `walk_arm` is the only
walker that does. Not reused for this question.

**Statuses, reported as separate columns, never folded:** `settled` (realized R), `horizon` (open at
40 sessions — `mark_r` at the last close is a MARK, never a return), `pending` (a daily row missing; the
walk blocks, never leaps), `abstain` (same-bar ambiguity). October names will mostly be `horizon` or
`pending`; the table says how many.

### 3.2 SECONDARY — fixed horizon, harness-independent (explicitly NOT the live exit)

For every entry under every option, from the fill: best high and the close over the next **20 sessions**
in budget-R and in own-R, and whether the placed stop was touched FIRST (daily low ≤ stop before the
high ≥ +3R; a same-day tie → `ambiguous`). This measures the tail the entry bought access to, independent
of the exit mechanics; it is reported beside the primary, never instead of it.

### 3.3 R frames (stated once)

- **budget-R** (headline, equal dollars across options) = `pnl_per_share / (anchor_high − placed_stop)`.
- **own-R** (the walker's native frame) = `pnl_per_share / (fill − placed_stop)`.
- **win** = settled realized budget-R > 0 after all legs. **big winner** = realized budget-R ≥ +3
  (settled), with marked `horizon` rows ≥ +3 counted separately as "marked". **tail R** = Σ max(0, R − 3).
- **worst loss** = min realized budget-R (settled), with the gap-through flag.

---

## 4. Calibration checks — run and PASSED before any option table is read

1. **Today's rule reproduces the stored SETUP fates.** On the rows with a `magna53` trade row
   (`entry_attempt=1`) whose fate is a fill, a `setup:*` skip or a `window:*` skip: the replay's path
   (stop-limit / limit / chase-cap skip / gap-below-floor / out-of-window / stop-too-wide / zero-range)
   must match `status` + `skip_reason`; a filled row's replay fill must be within 0.5% of
   `entry_price`; REGN's replay must refuse at planned $52.38 vs actual ≥ $78.57. **Rows the live system
   stopped for a NON-setup reason — `block:*` (position cap, breakers, daily loss, phase) or `infra:*`
   (no bar, account fetch) — are NOT mismatches:** the replay carries no account state and enters them;
   they are listed as "replay enters, live did not (non-setup reason)" and stay in every option's
   population (the repo's "real EPs regardless of safeguards" rule). The proxy error (proxy vs the
   stored latest, §2.1.3) is printed per row; if its median |error| exceeds 0.3% the sensitivity proxy
   becomes primary and the plan says so here.
2. **The depth walk reproduces the recorder.** For every fill with a `live_replay` row in c1 `CF` whose
   `exit_era` is the depth era (`exit_rules_json` carries the depth keys), the offline walk on the same
   fill/stop must return the same `realized_r` (±0.01), `final_reason`, `exit_session`. Pre-10-13 fills
   were walked by the recorder under era D (plain trail) — they are NOT compared to the depth walk
   (different rule era; "never pool rule eras"), only listed.
3. **Stored 09:30 bar = the live ORB bar.** `POP.orb_open/high/low` vs the `orb_bar_fetched` summary's
   O/H/L for every ticker-day that has one; any mismatch is listed and that row's ORB is taken from the
   audit row (what the live decision used).
4. **Population integrity.** `CHECKS.pop_rows = 51`, `with_0930_bar` and `COVERAGE` named per row;
   `MINCOUNT.min_rows` equals the number of MIN lines parsed.

A failed check stops the study at that check; the fix is reported with the check, and the option table
is not read until the check passes.

---

## 5. The table to him (one table, budget-R)

All columns at the 20-session decision horizon (§3.1); a last column carries the 40-session big-winner count.

| option | enter (of 51) | same as today | settled / horizon / pending / abstain | win share | big winners ≥ +3R (settled ∣ marked) | tail R Σ(R−3)⁺ | sum R | worst loss (budget-R) | names it adds / drops vs today | ≥ +3R at 40 sessions |
|---|---|---|---|---|---|---|---|---|---|
| today | | — | | | | | | | — |
| (a) crossing-bar anchor | | | | | | | | | |
| (b) opening gap ≥ floor | | | | | | | | | drops: … |
| (c) cap from the floor | | | | | | | | | adds: … |
| (c′) + size on the floor risk | | | | | | | | | sensitivity |

Below it: the composition table (§1), the admission-era split (pre/post 08-27) as a second block if the
direction differs, and the §3.2 fixed-horizon tail per option (reached +3R within 20 sessions; stop first).

---

## 6. Recommendation rule — stated in advance

Baseline = today's rule replayed on the 51 under the current exit (§3.1), read at the **20-session
decision horizon**; the 40-session walk informs the runner column only.

An option is **recommended** only if ALL of:
1. **Sample:** it enters ≥ 10 of the 51 (CHANGE_PROCESS N ≥ 10) and ≥ 6 of those are `settled` at 20
   sessions.
2. **More or equal access:** it enters at least as many of the 51 as today — except (b), which can only
   remove, and is recommended only if the names it drops have a negative sum of realized budget-R AND
   contain no big winner (settled or marked).
3. **Tail not worse:** big winners (settled) ≥ today's, and tail R ≥ today's.
4. **Sum better:** sum of settled realized budget-R ≥ today's + 2.0.
5. **Worst loss bounded:** worst single loss ≥ −1.6 budget-R (the cap's own bound of 1.5× plus one
   gap-through), unless the option is (c) and the (c′) sizing variant brings it inside — then the rec names
   (c′), not (c).

If no option clears all five → **rec = keep today's rule**, and the REGN shape is filed as a watch item
with the count of names it affected (the population grows ~2 a week). If more than one clears → the one
that changes the fewest of today's trades ((b) < (c) < (a)). If the pre-/post-08-27 cohorts disagree in
direction, the post-08-27 cohort decides and the disagreement is stated. The rec is a line under the
table; the decision is his.

---

## 7. What the data cannot answer (known before the pull)

- **The true latest trade / ask at submit.** Only a minute-bar proxy exists (§2.1.3); a cap verdict within
  ~0.2% of the limit can flip on a tick. Rows inside that band are flagged `borderline` in the table.
- **Limit-fallback fills.** Assumed at the limit when the bar's low ≤ limit; the live ask-aware path
  (`entry_ask_aware`) and partial fills are not modelled.
- **Pre-market prints.** `mi_intraday_bars` stores RTH bars for alerted ticker-days only; a flip-up whose
  first ≥-floor print was pre-market has no crossing bar before 09:30 — under (a) its crossing bar is the
  first RTH bar that reaches the floor, which may be the 09:30 bar.
- **Minute gaps.** A ticker-day with a hole inside 09:30–10:00 can hide the crossing bar or the fill;
  `COVERAGE` names them and the walk abstains rather than guesses.
- **Recent names.** Entries from the last ~8 weeks cannot settle a 40-session walk: `horizon` rows carry a
  mark, `pending` rows nothing. The table says how many; a mark is not a return.
- **Admission under a different anchor.** (a)/(c) change the ENTRY, not the grade; whether a name would
  have been graded HIGH had the anchor been different is not a question bars can answer.
- **Size / account effects.** Shares, the 20% notional cap, the position cap and breakers are outside the
  per-share frame; budget-R already states the dollar risk at equal budget.
- **Era.** The 51 were ADMITTED under the rules of their day (floor 10%→9% on 08-19, real-time authority
  08-27, HIGH ≥ 65 everywhere 08-22); the replay applies today's ENTRY and EXIT mechanics to all of them —
  that is the "replay raw bars under current rules" discipline, and the admission split is reported, not
  pooled away.
