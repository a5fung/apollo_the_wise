# #395 — coil-finder shadow → real entries: GO/NO-GO evidence (Lane-1 pre-build, 2026-07-11)

**The decision (due Mon 7/14, ruled at the Lane-1 sitting):** flip the Family-A consolidation
**Anticipate** entry (the coil-finder, ADR 0013) from shadow → real paper entries? Gated on the
#327 forward-shadow proving a live edge (the #326/dossier question the offline harness structurally
could not answer). This is the read of the LIVE shadow (`mi_consolidation_entry_shadow`, prod,
read-only) — no new probe needed; the shadow settled itself.

## The evidence

| entry_mode | N settled | mean R | median R | win% | read |
|---|---|---|---|---|---|
| **anticipate** (coil-finder, the #395 subject) | **34** | **−1.23R** | **−1.00R** | **18%** | losing distribution |
| confirm (the #354 flag→Confirm entry) | 7 | −0.11R | −0.23R | 29% | ~breakeven, N too small |

**The anticipate distribution is genuine, not an artifact:** 11 clean −1.00R stopouts (the initial
stop), a spread of real losers (−13.98R gap-down tail, −3.45, −3.20…), and real winners
(+2.00R ×3 target hits, +1.73, +1.34). It settles as a true momentum-loser shape: **most stop
out (18% win), the mean is dragged NEGATIVE by a gap-down tail** — the *opposite* of the
tail-carried-POSITIVE shape the edge cases require.

## The read → NO-GO (recommendation)

1. **The coil-finder Anticipate entry shows NO live edge** — −1.23R mean / −1.00R median / 18%
   win over 34 settled forward-shadow trades. Flipping it to real entries would ship a
   measured-losing setup (THE LINE + the evidence both say no).
2. **This CONFIRMS the offline prediction** (edge dossier §5 · `ninem_consolidation_vs_day2_replay_327`):
   Phase-A's +2.00R was a daily-close-confirmed **selection artifact**; Phase-B re-timing to the
   actual first-intraday-break dropped it to ~−1.00R filled median. The live watcher delivered
   **−1.23R** — the pessimistic re-timing was right. The offline harness could not answer the
   live-edge question; the forward shadow now has, and the answer is negative.
3. **The `confirm` mode (N=7, −0.11R)** — the #354 Confirm entry — is too small to read and only
   marginally-negative; it has NOT earned a GO either. Its shadow keeps accruing.

## Consequences for the sitting

- **#395: NO-GO** (rec) — do not flip the coil-finder to real entries.
- **#353 (consolidation→paper graduation): stays GATED** — there is no edge to graduate; the
  #327 gate it waited on has resolved NEGATIVE.
- **ADR 0026 (consolidation-family unification) context:** the entry mode that's actually been
  shadow-tested (Anticipate) is the losing one. The ADR's NEW entries (Confirm via #94, U&R via
  reclaim) have thin/no shadow yet — 0026's value is now more about *reconciling the machinery*
  than about a proven Anticipate edge. Worth the operator's eye at the sitting.

## The honest fork (operator's call at the sitting)

- **NO-GO now** (rec): formally kill the coil-finder→real path on this evidence; keep the shadow
  running only if there's a specific hypothesis for why a parameter change would flip the sign
  (there isn't one on the table). Frees the slot/attention for the dossier's higher-EV levers
  (peak-lock, concentration cap, judge promote-arm).
- **Keep-observing** (alternative): the anticipate N=34 is modest; wait for +N. But the sign is
  negative AND predicted-negative — this is not a sign-ambiguous "need more data" case; it's a
  "the evidence agrees with the pessimistic prior" case. Continuing to shadow a −1.23R setup with
  no flip-hypothesis is sunk cost.

*Read-only; no trade/shadow change made. Feeds the Lane-1 sitting (#459) + the #425 declaration
walk's honest-edge ledger (a designed setup that the forward shadow retired — the process working).*
