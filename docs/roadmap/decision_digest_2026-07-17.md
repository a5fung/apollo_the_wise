# Decision Digest — Friday 2026-07-17 (one sitting, ~35-45 min)

**Timing: MORNING if possible** — every ⚡ below unblocks same-day work, and
the deploy wants items 1-2 signed before it goes out (reshaped plan 7/16
night: Friday = ship + verify + the next premortem wave; the original Friday
builds were consumed Thursday night).

The push plan's single batched operator sitting. Each item = one line to rule;
"ok" is a complete answer. Items marked ⚡ unblock a same-day close.

## Sign-offs (built, tested, waiting on your word)

1. ⚡ **#469 promote-wall allowlist** — denylist→allowlist inversion; zero
   behavior change for the 3 current lanes; unknown future sources default
   OUT. → "ok on 469" and it rides the deploy.
2. ⚡ **#436 proposal expiry** — unconfirmed staged-paper proposals now expire
   after their ORB day (status='expired'; the ABSI-class + the stale-confirm
   sharp edge die). → "ok on 436".
3. **#452 Stage-2 forks** (concentration gate — telemetry is live from today):
   F-A cap=2/family (rec) · F-B no game_changer exemption (rec) · F-C DB-toggle
   dark-ship (rec) · F-D stems now, ecosystems later (rec). → "approve recs" or
   name changes; the replay backtest card runs before any flip regardless.

## Rulings (one line each)

4. **F2b — promote broker-order ingest dry_run → live_r1?** Dry-run clean
   since 7/13 (~4 weekdays by tonight). THIS IS THE v1.0 LONG POLE: promoted
   Fri → FL-4 completes ≈7/23 → declaration ≈7/23-24. → "promote" / "wait".
5. **#197 cap+1 shadow at N=27/30** — rule "27 is enough, review now" or let
   it ripen (~days). → "review now" / "wait for 30".
6. ⚡ **#416 M&A guards** — close on replay+smoke evidence (5-ticker flip set
   verified with shipped code; live per-path fire hasn't occurred) or keep
   event-gated. → "close" / "keep".
7. ⚡ **#306 giveback** — fold the remaining verify into the existing
   giveback_shadow_review gate (8/06) and close the task? Plus: bless the
   BACKFILL acceleration (replay the real closed live trades since 6/22
   through the shadow — honest evidence, weeks earlier). → "fold + backfill" /
   "fold only" / "leave".
8. ⚡ **#269 'promote-cap eval harness'** — 4 words, zero recoverable scope
   (AKTS half verified: judge promote → +16.1%). What did you mean — judge
   daily promote cap · theme graduation cap · drop it? One word closes it.
9. **#357 Persistent Sugar Babies role** — the 3rd stream's disposition
   (kept the original task detail; your call from its options).
10. **#299 P2 tape-features funding** — yes/no on the data spend.
10b. **#476 biotech fork (A/B)** — the overnight diagnosis found the REAL killer:
    the March `biotech → max_themes=0` sector-cap silently drops every biotech
    theme in Pass 2 while the shadow-promote resurrects the cohort nightly
    (NOT the protect-strip; NOT fixed by Phase 2 being armed). Methodology
    call: **(A)** re-include biotech (cap 0→2 + containment canonicalization →
    cohorts crystallize into E-BIO; weak rec — the RS-side biotech filter was
    already walked back, the theme-side wasn't = internal inconsistency) vs
    **(B)** suppress biotech at discovery (orphans become working-as-designed).
    → RULED A 7/16 night + BACKTEST ALREADY RUN. One amendment to sign:
    the replay shows the stream holds 5-6 family lineages, so the cap must be
    **1-per-family (≤6), not a global 2** (a global 2 leaves 37/48 cuts dying).
    Mush guard passed all 24 grid cells; 5/12 elite home via the replay, the
    rest via the assignment pass post-ship (forward criterion ≥10/12 in 5 runs).
    → "ok per-family cap" and the build starts.
    Docs: 476_biotech_crystallization_diagnosis_2026-07-17.md ·
    476_optionA_backtest_2026-07-16.md

## Operator-minutes actions (~5-10 min each, each unblocks a close)

11. ⚡ **#195** rotate the portfolio-app2 app_password.
12. ⚡ **#280** create the staging paper account (I wire keys after).
13. ⚡ **#420** create the UptimeRobot account (I wire the endpoint after).
14. **#384** X account: check credits + rotate the leaked-to-local-transcript
    creds; then your `_X_POSTING_ENABLED` flip call.
15. ⚡ **#194** provide the dashboard deploy key — unblocks the daily
    trades+themes auto-export AND #472 (the ecosystem view on the dashboard),
    both then land Sunday.

## FYI (no decision needed)

- #468 realized-R study: MODERATE ≥ HIGH on identical bracket sim; the 70-79
  score band is a −0.26R hole while 60-69 is the best band — converges with
  the B6 inversion; the lever is Saturday's meta-rubric work.
- #425 walk pack refreshed: blocking 11→8; Saturday's walk agenda is 4 items,
  ~20 min; declaration ≈7/23-24 pending item 4 above.
