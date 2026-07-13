# v1.0 READINESS RED-TEAM — findings register (Fable, 2026-07-12)

> **VERIFICATION (Opus, against code — 2026-07-12). All 3 REDs CONFIRMED** (no over-rating this pass):
> - **RED-1 — CONFIRMED, one framing nuance.** `v1_closeout_status.py:68` hardcodes
>   `FL1_SOAK_START = date(2026,6,30)` and never resets; #425 says "PULL EARLIER the moment the
>   countdown shows green" → auto-pull ~7/15 onto the meter, contradicting the walk-pack's strict
>   ruling (reset 7/7 → 3/10). Nuance: the reap exclusion (lines 84-87) is a *deliberate,
>   operator-signed* 7/6 ruling, not a blind spot. Real RED = the two-clocks + auto-pull.
> - **RED-2 — CONFIRMED.** `compute_fl1` resets only on an L1 breach or 4 hardcoded
>   `MANUAL_REPAIR_EVENT_TYPES`; a terminal `stop_ack_remediation_failed` (naked) counts as a clean
>   soak day. Real fail-open in the declaration's spine.
> - **RED-3 — CONFIRMED.** `_EXPECTED_JOBS` (audit_invariants.py:473) watches only 3 jobs — the 16:12
>   equity-snapshot (feeds the breaker) is absent; `drawdown_check_unavailable` lacks "error" so the
>   `%_error` nightly alert misses it. The breaker can fail-open silently. Real monitoring gap.
>
> **Fix status:** RED-2 + RED-3 in implementation (measurement/monitoring only — THE LINE intact);
> RED-1 wired as a #425 auto-pull gate. Live-fill YELLOW resolved: MAGNA53 filled 3× (WULF/CRCL/WDFC,
> verified) — #413 tracks a different first-fill; surface-labeling, not a real gap.

**Scope**: the v1.0 declaration itself (#425, walk ~7/22) — FL-1..FL-8 minus the trade-state
composition slice (already covered: `composition_redteam_2026-07-12.md`). Method: adversarial
read of the walk pack + done-done map against the actual measurement machinery
(`scripts/v1_closeout_status.py`, `audit_invariants.py`, `infra/*.sh`, `infra/restore.sh`,
`docs/setups/safeguards.md`, PLAN.md). **THE LINE**: everything below is a finding + a proposed
operator decision. Nothing was changed.

**Honesty note on method**: prod DB reads were denied in this session, so the FL-1 meter's
*actual current reading*, the live fill/closed-trade count, and the presence/absence of L1
rows 6/30→7/12 are cited as *unverified* — each is marked "QUERY AT WALK" where it matters.
Everything else below is verified from the repo at HEAD (`5c14a74`).

---

## RED — declaration-threatening

### RED-1 · FL-1 has two conflicting clocks, and the one that triggers the declaration cannot see the repairs the recommended ruling counts

**Asserted**: walk pack F1 — strict ruling (REC): the 7/6 phantom reap + 7/7 jsonb cleanup
were repairs → clock reset 7/7 → **3/10** as of 7/12 → completes ≈ 7/22.

**Actually measured**: `scripts/v1_closeout_status.py` (the #426 countdown that rides the
evening briefing) computes FL-1 from `FL1_SOAK_START = 2026-06-30` (hardcoded), resetting
only on (a) L1 `anomaly_detected` level-1 rows and (b) four allowlisted
`MANUAL_REPAIR_EVENT_TYPES`. Neither 7/6 nor 7/7 registers:

- `phantom_pending_confirmation_reaped` (7/6) is **explicitly excluded** from the allowlist
  (operator-signed 7/6: "DB hygiene, not a repair" — v1_closeout_status.py:84).
- `scripts/fix_double_encoded_exits_287.py` (7/7) **emits no audit event at all** — it is
  invisible to any query, under any ruling.

So unless an L1 fired in the window (QUERY AT WALK), the mechanical countdown reads ~8/10
today and shows **10/10 ✓ around 7/15–16**. PLAN #425 then instructs: *"PULL EARLIER the
moment #426's countdown shows all clocks green (earliest ~7/17)."* The anti-idle trigger
actively pulls the declaration up to a week early onto exactly the "soak containing manual
repairs — hollow" outcome the walk pack itself warns against.

**Second-order problem**: ruling F1 strict silently **reverses the operator's own 7/6 signed
ruling** (reap ≠ repair, recorded in the meter's code comment). The walk pack does not
surface that as a reversal. CHANGE_PROCESS discipline for reversals (articulate why the
prior ruling was *wrong*) applies to the ruling itself.

**Severity**: RED. FL-1 is THE pacing gate; its driving surface measures a different soak
than the one being ruled on.

**Blocks 7/22**: YES — but the fix is one sitting + one small change.

**Proposed operator decision**: rule F1 at the walk-pack review as planned, AND in the same
sitting direct the meter to equal the ruling: if strict → `FL1_SOAK_START = 2026-07-08` (or
add the two repair dates to the reset set) so the countdown, the briefing line, and the
ruling are one number; explicitly note the 7/6 reap-ruling reversal. If lenient → say so and
accept the walk pack's own "hollow" caveat in §8. Until ruled, treat the countdown's FL-1
digit and its "pull earlier" trigger as **not authoritative**.

### RED-2 · The FL-1 "repair-class event" reset set is fail-open in both directions — it cannot distinguish a clean soak from a silently-repaired one

**Asserted**: FL-1 evidence pointer = "mi_audit_log: zero repair-class events since 7/7."

**Actually verified**:
1. The repair-class set is a hand-curated allowlist of 4 historical event types. Its own
   docstring: *"a future incident with a novel event-type name would be silently missed
   until this list is extended."* The 7/7 repair is the existence proof — an
   operator-reviewed, committed repair script that emits **nothing**. A raw
   `docker exec psql UPDATE` would likewise emit nothing. "Zero repair-class events" is
   therefore consistent with any number of unlogged repairs; the evidence is vacuous as
   stated.
2. **The blind spot the mission asked about is real**: automated-remediation *failure* days
   do not reset the clock. `check_naked_position` (the L1 leg) only sees DB-side
   `stop_order_id IS NULL`; a day where a live position sat broker-naked, the stop-ACK
   watchdog fired, and the fallback stop FAILED (`stop_ack_remediation_failed`, CRITICAL
   Telegram) is neither an L1 breach nor an allowlisted repair event — it counts as a
   **clean soak day**. Same for `infra_halt_state_unreadable` days and
   `cross_account_event_rejected` days.

**Severity**: RED (measurement integrity of the headline gate).

**Blocks 7/22**: the walk-day query does; the standing fixes can trail.

**Proposed operator decisions**:
- (a) Walk-day FL-1 evidence = a **negative query the operator eyeballs**, not the allowlist
  count: all distinct `mi_audit_log` event_types in the soak window + `git log` of anything
  under `scripts/` touching `mi_live_trades` in the window. (QUERY AT WALK.)
- (b) Standing rule (small card): every future repair script MUST emit one common
  `manual_trade_state_repair` audit event (single constant; #151 discipline gates it) — kills
  the novel-event-name hole permanently.
- (c) Operator signs the exact FL-1 reset set, explicitly ruling whether
  `stop_ack_remediation_failed`-class days (remediation FAILED, not remediation ran) reset
  the soak. Rec: yes — a failed safety-net day is not a clean day.

### RED-3 · FL-2: the ACTIVE drawdown breaker has a documented fail-open whose trigger nothing monitors

**Asserted**: FL-2 = "mechanical safety, fences exercised," ~85%, two drills remaining.

**Actually verified**: the breaker's stale-data guard (safeguards.md, advisor-flagged;
`drawdown_breaker.py:27`) **fails OPEN**: if the newest `mi_account_equity_snapshots` row is
>48h old, the breaker is "effectively disabled until data freshens." The trigger path is
unmonitored end-to-end:

- The 16:12 job's per-mode failure path is `logger.error` + `drawdown_check_unavailable`
  audit row only (`scheduler.py:1370`); `notify_job_failure` fires only on the outer
  import-level exception.
- `drawdown_check_unavailable` does **not** match the `%_error` pattern → invisible to the
  `check_audit_error_window` L1 and the 3-bucket morning error banner.
- `account_equity_snapshot` is **not** in `_EXPECTED_JOBS` (`audit_invariants.py:473` — only
  morning_briefing / nightly_data_pull / evening_briefing) → the job-no-show L1 never fires.
- The 16:13 kill-scale eval Telegrams only on band *transitions* — stale inputs produce no
  transition → silent.
- No L2 metric watches snapshot freshness (verified: no such MetricSpec).

Net: a multi-day 16:12-hour failure (Alpaca hiccup at that hour, DB write fault, wedged job
— anything that doesn't kill the container, which the watchdog would catch) silently disarms
the multi-day equity guard while entries continue (the entry-time account fetch fails
CLOSED, but it is a different call at a different time and can keep succeeding). FL-2 would
be signed "mechanical safety complete + hardened" over a known, unmonitored disarm path on a
live-money safeguard.

**Severity**: RED for the *claim* (the residual protections — daily-loss, per-trade sizing,
/pause — still stand, so this is not an uncovered account).

**Blocks 7/22**: recommend YES — the fix is a ≤half-day telemetry card and is exactly the
class of hole the declaration exists to certify closed.

**Proposed operator decision**: approve a monitoring-only card (no safeguard behavior
change, THE LINE intact): add `account_equity_snapshot` to `_EXPECTED_JOBS` **or** alert on
any `drawdown_check_unavailable` / on a missing daily snapshot per active mode. The
fail-open semantics themselves stay as designed.

---

## YELLOW — signable, but only with eyes open (each needs an explicit ruling or a named caveat in §8)

### YELLOW-1 · FL-2's "every safeguard live-exercised" — the honest ledger disagrees with ~85%

- **daily-loss halt**: never fired live; the synthetic drill is deferred to WALK DAY
  (checklist item 2). If the drill finds a bug, the declaration slips with zero margin.
  *Propose: run it THIS week, not at the walk.*
- **drawdown per-mode transition**: live-mode transition rows almost certainly do not exist —
  the live book (~−$71 on ~$5k ≈ −1.4%) has never reached the −4% WATCH tier. "Pull the
  audit rows" will return paper-mode evidence only. The criterion as written ("per mode") is
  unsatisfiable in-window. *Propose: operator explicitly accepts paper-mode transitions +
  shared-code-path argument as the evidence, amending FL-2's wording at the walk — not
  letting it pass silently.* (QUERY AT WALK: confirm live-mode row absence.)
- **max-positions block**: the on-record LIVE exercise (7/6, the phantoms) exercised the
  **old** counting predicate; #436 fork B changed `OPEN_POSITION_STATUSES` on 7/11. Current
  cap code: tests + preflight, no live block on record. Label it "exercised-then-modified."
- **/pause**: FL-2 row cites "verified in code"; the criterion demands a LIVE exercise; last
  live verify = 6/22 runbook. *Propose: 60-second after-hours /pause → /resume re-drill in
  walk week.*
- **circuit_breaker**: deprecated-but-still-active; the promotion plan's 30-day removal step
  (armed 6/3) is >30d overdue. Cosmetic; sign-or-schedule so the SSoT stops disagreeing with
  the code.

### YELLOW-2 · FL-7: "market-gated verify-lives close themselves during the soak" is optimistic on three axes

1. **#150 is unforceable** (share-reservation-lag race; hasn't recurred since 5/09). It is in
   the meter's `BLOCKING_TASK_IDS`, and the closeout doc's own DoD says "re-date honestly if
   no event" — i.e. FL-7's "every BLOCKING task closed" is **not reachable by waiting**. The
   walk pack pre-argues F1/F2 but has no fork for this. *Propose (rec): rule #150 a standing
   watch-item — non-blocking for v1.0, with its alert-on-event verification wired — and apply
   the same ruling template to any event-gated verify that hasn't fired by walk day.*
2. **Events don't close tasks; walked checklists do — and the surfaces already disagree.**
   The done-done map asserts "N=3 closed / −$71" live trades; PLAN #413 (pending, 7/17) still
   says "a real-money position has never FILLED"; #183 says "awaits first live fill"; the
   composition evidence references WULF as a live 7/6 position. At most one of these is
   current. Either closed live trades exist and two blocking first-fill/first-exit
   verification checklists that should have been walked at those events were not, or the N=3
   headline in the declaration's companion map is wrong. *Propose: reconcile with one
   mi_live_trades query at the walk (QUERY AT WALK) and walk any owed checklists before
   signing FL-7.*
3. **The blocking meter is a frozen 7/5 snapshot.** Blocking-class hardening filed since —
   #443 (live alert mislabel, 7/8), #463 (finalizer-lock money-path bundle, 7/12), #452
   (correlated-book stage-1) — is invisible to the countdown's "blocking N open," which
   therefore undercounts by construction. *Propose: FL-7 walk evidence = check_plan + a
   hand-check of post-7/5 tasks against the BLOCKING rubric, not the countdown digit.*

### YELLOW-3 · FL-4: the green path needs evidence a healthy system produces at rate ~0, and the meter measures a different thing than the gate

- F2's sign-off path — "≥3 clean R1 proposals → sign `live_r1`" — requires *untracked broker
  orders to actually occur*. R1 proposals fire on exactly the drift the last month of
  hardening exists to prevent; 5 clean days can produce zero proposals, leaving the gate
  unsatisfiable on live evidence. *Propose pre-ruling: the #184b paper-exercise proposals
  (real paper-Alpaca orders through the same code path) count as the sign-off evidence (rec),
  or accept an open-ended FL-4 slip.*
- `compute_fl4` counts drift-quiet days since 7/6 **regardless of promotion state** — the
  briefing clock can read "5/5 ✓" while the ingest is still dry_run/dark. Same
  meter-vs-ruling divergence class as RED-1; fold into the same fix sitting.
- **Date honesty**: even on the pack's own numbers, FL-4 green ≈ 7/24 > soak-complete 7/22.
  The earliest internally-consistent declare date is **7/24**, not 7/22, unless the operator
  re-bases F2's quiet-days.

### YELLOW-4 · FL-3 / FL-5: the streak is real, but the perimeter has named holes the RTO claim leans on

- **Whole-host death is silent** — the watchdog's own header admits it runs on the host it
  watches; #420 (external pinger) is open and blocked on operator action (7/16). The 95-min
  RTO clock starts at *detection*; until #420, overnight/weekend detection is unbounded
  (first human signal = a missed briefing). *Propose: #420 lands pre-declare — the only
  operator cost is creating the pinger account.*
- **The 7 green nights were measured against a spine that changed mid-streak** (watchdog +
  fixes deployed 7/5–7/12; the #463 watchdog-episode fix debuts Monday 7/13). "Keep green
  through the walk" is the right mitigation — make it explicit: the streak at signing must
  include ≥5 nights on the FINAL spine.
- **Full-path DR is 4+ weeks stale at declare**: last throwaway-box rehearsal 6/20 (#349).
  Everything since — the roles.sql bundle path through restore.sh Phases 5/8, ops_lib.sh,
  watchdog state dirs — is covered only by the nightly restore-check, which exercises Phases
  7–8 (DB + roles) and nothing else. The nightly fence is genuinely good (run-1 catching
  `dashboard_ro` on 7/5 proves it), but Phases 1–6 and 9–11 are unexercised since 6/20.
  *Propose: one throwaway-box rehearsal in walk week, or sign FL-5 with "restore.sh tail
  unexercised since 6/20" named in §8.*
- **FL-5 single point of failure**: ONE Google account is the root of trust for BOTH recovery
  legs — the gdrive folder (dump + secrets blob) AND the GPG passphrase (Google Password
  Manager) AND the gdrive OAuth. Account lockout/compromise = no dump, no secrets, no
  passphrase, simultaneously. *Propose (post-declare acceptable): offline/second-channel copy
  of the passphrase + a periodic second-location copy of the newest backup pair.*
- **RPO honesty**: 24h RPO on a live trading book means a mid-session host death loses the
  day's audit/shadow/settlement rows (positions themselves are broker-safe). Documented and
  reasonable — but it is part of what the §8 signature accepts; name it.

### YELLOW-5 · The signature's meaning: three known money-path defects are scheduled AFTER "complete + hardened"

None of these violates an FL criterion as written; all three contradict a naive reading of
the D1 definition. They belong on the §8 page as named exclusions, not in the operator's
peripheral vision:

- **#464** (8/1): every alpaca-py call is bare-sync inside async — a hung Alpaca endpoint
  freezes the entire event loop *including the WS fill handlers and the reconcile safety
  net*. Latent-chronic since day 1.
- **#465** (8/1): `UNIQUE(ticker, alert_date)` has no account_mode — a paper row silently
  suppresses a live entry on the same ticker/day (fail-safe direction, but live entries can
  be silently lost to paper activity).
- **#452** (stage-1 telemetry only): no correlation/family gate — 5 same-family HIGHs can
  fill all 5 slots = one ~100%-deployed bet; the 7/11 premortem's TOP risk; the edge dossier
  ("one correlated wipeout erases a year") makes the same point.

*Propose: §8 carries a "known-open at declaration" list (these three + anything from
YELLOW-1/2 the operator waives) with dates — the declaration then states what "hardened"
excludes, which is what makes it honest.*

---

## GREEN — verified ready (real results; no manufactured REDs)

- **FL-8**: 4 consecutive Sundays, DB-measured (`mi_system_reviews`, `window_days=7`); the
  meter matches the definition exactly. GREEN.
- **FL-3 mechanics quality**: restore-check + service watchdog are well-built — file-based
  dedup state (works when postgres is down), run-locks, docker-inspect timeouts (hung-daemon
  class), fenced Telegram text (the 7/5 400-lesson), the EXPECTED_ROLES drift fence parsing
  restore.sh's own source line (single-list discipline), and a run-1 that caught a real DR
  gap. GREEN, with the YELLOW-4 perimeter caveats.
- **FL-6**: build complete 7/12 (S-C spend appendix; /cost board + budget alert already
  armed); verify-live 7/19 lands pre-walk; the $11.75-vs-$10-placeholder finding shows the
  surface does its job. GREEN-track pending the 7/19 verify.
- **#183 enum-boundary work**: exhaustive audit, fix deployed 7/7 both scopes,
  container-verified, 12 gates; the remaining market-gated verify is honest. The
  `audit_invariants:116` false-naked leg (which would have made FL-1's L1 signal *noisy*,
  not blind) was fixed in the same deploy. GREEN-track.
- **The walk-pack idea itself**: pre-arguing F1/F2 with recs, evidence pointers per FL, and
  a same-sitting D-ladder blessing is the right shape. The gaps above are in the meters and
  two un-argued forks, not the structure.

---

## VERDICT

v1.0 is **not honestly declarable on 7/22 as the pack stands, but it is close and the
substance is mostly real** — the institution's machinery (watchdogs, restore-fence, audits,
learning loop) verifies well; the gap is that the headline gates are certified by meters and
prose that don't measure the ruled definitions. The single most dangerous interaction is
RED-1: the strict soak ruling the pack recommends is invisible to the countdown that #425
says to "pull earlier" on — declaring on that meter signs a soak containing the 7/6–7/7
repairs, the precise "hollow" outcome the pack warns against. MUST close before signing:
(1) rule F1 and make the meter equal the ruling in the same sitting (RED-1); (2) walk-day
FL-1 negative-evidence query + the standing repair-event rule (RED-2); (3) the
drawdown-fail-open monitoring card (RED-3); (4) daily-loss drill this week, not walk day;
(5) rule the #150/unforceable-verify fork and reconcile the fill-count contradiction
(YELLOW-2). If the operator declares with the remaining YELLOWs open, they are signing, with
eyes open: paper-evidence-only for the live-mode breaker transition, a restore.sh tail
unexercised since 6/20, host-death detection that depends on a human noticing silence until
#420 lands, and three named money-path defects (#464 / #465 / #452) as post-v1.0 debt.
Earliest internally-consistent date if F2 flips Monday and the MUSTs close: **~7/24**
(FL-4-bound), not 7/22.
