# #479 — Telegram EOD noise + evening-brief cut (proposal for operator ruling)

Goal (operator 7/16): "high signal — surface what is actionable and critical."
Target: a normal post-close day = **2 messages** (one close digest + one
evening brief ≤1 Telegram message), real-time alerts only for fills/stops/
real errors.

## 1. The post-close sender inventory (15:45–21:00 ET)

| ET | job | today's Telegram behavior | PROPOSED |
|---|---|---|---|
| 15:45 | partial_exit_scan | per-exit notice | KEEP real-time (it's a fill) |
| 16:00 | intraday_signals_eod_digest | 1 msg (5 detectors) | → fold into Close Digest |
| 16:05 | eod_cleanup | cancel notices | fold (count only; detail on real error) |
| 16:10 | eod_ep_recap | 1 msg | → fold |
| 16:12-16:15 | equity snapshot · post_eod_audit | L1/L2 breach alerts only | KEEP (already actionable-only) |
| 16:18 | book_concentration (new) | flag-only | KEEP (already silent-normal) |
| ~16:2x-16:4x | 9m_pace_digest · judge_delta_digest · news_quality_drift | 1 msg each | → fold |
| 16:45 | live_position_update | 1 msg (stops/trails) | → fold (book section) |
| 17:05 | shadow-promote 🎓 | new-grads only | KEEP (rare, actionable) |
| 17:52 | spend_alarm (new) | breach-only | KEEP |
| 18:00 | evening_briefing | ~3 msgs | → 1 msg (cut below) |
| 21:00 | evening_position_backstop | sync-discrepancy only | KEEP |

Net: **~6 routine messages fold into ONE "Market Close Digest" at 16:55 ET**
(after the position update, before the nightly chain). Real-time/actionable
alerts unchanged. Self-healing/transient stays audit-log-only (house rule).

## 2. MOCK — the AFTER state (a normal day = these 2 messages)

### Message 1 — 🔔 Market Close Digest (16:55 ET)
```
🔔 CLOSE — Fri 7/17
BOOK  2 open (MANE-class): AAAA +1.2R stop@BE · BBBB −0.3R stop 118.02
      1 partial taken (CCCC 33% @ +2.1R) · 0 stops hit · 1 unfilled cancelled
EP    2 HIGH (1 filled, 1 LULD-rejected) · 3 MODERATE → briefing
9M    pace 3/20 (detection only — Day-2 strategy deprecated, no line)
JUDGE 2 promotes, 1 downgrade (detail: /judge)
SIGNALS 5-detector day: 2 flags, 1 fishhook (detail: /detectors)
⚠ news-quality drift: none
```
One message, monospace block, every line collapsible to its existing
drill-down command. Sections with nothing to say are OMITTED (a quiet day
is 4 lines). Deprecated strategies get NO line (operator 7/17: 9M Day 2 is
not an active setup — detection-layer pace only, and only when non-empty).

### Message 2 — 🌙 Evening Brief (18:00 ET, ≤4096 chars)
KEEP: title+closeout line · regime (1 line) · ecosystem scorecard (top-5
compact, exists) · top-10 RS leaders (one code block) · live-book line ·
actionable watch items (≤3).
CUT to on-demand: unanchored (→/watch) · velocity+turners (→/watch all) ·
pullbacks (→/ideas) · wick/fishhook stats (→/detectors, /fishhook) ·
sugar-babies section (→/sugarbabies) · EP-outcomes stats (→/eps).
Detail is demoted, never deleted — every cut section names its command.

## 3. The ruling needed (one word each)
- **R1**: approve the fold list in §1? (any digest you want kept separate?)
- **R2**: approve the brief cut list in §2? (any section you want kept?)
- **R3**: digest time 16:55 ET ok?

Implementation after ruling: one consolidated digest job + render, the
per-digest jobs flip their Telegram sends to digest-contributions (audit rows
unchanged), briefing section list trimmed. Observability-only (THE LINE).
DoD: next normal close day = 2 messages; operator confirms signal quality.
