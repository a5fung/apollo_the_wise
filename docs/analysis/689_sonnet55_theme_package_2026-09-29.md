# Sonnet 5.5 and the theme prompts — root cause, the fix, and old-vs-new (#689, 2026-09-29)

## 1. The answer first

- **Root cause.** `claude-sonnet-5-5` answers a prompt that makes it write its reasoning out in the answer
  ("Reason FIRST:", "Fill analysis_scratchpad FIRST", per-stock reasoning in `analysis_scratchpad`) with
  `stop_reason: "refusal"` and no output — on most runs, not all. Thinking settings, the finance subject and the
  child/parent wording were each varied alone and ruled out.
- **The package (his yes, 2026-09-29):** drop the pre-verdict `analysis_scratchpad`; put a short reason AFTER the
  verdict (`no_fit` on assignment, `declined` on discovery, `reason` on split); the model reasons in its own thinking.
- **With it, every theme job answers on 5.5**: assignment 15/15 over 3 batches, EP theme-fit 15/15, discovery 8/8,
  split 6/6, rename 3/3, validation and narrative discovery 6/6.
- **Money path:** the new setup confirms MORE EP theme fits (5 of 44 vs 0–2 of 44). The extra confirmations come from
  the PROMPT change, not the model — the new format on Sonnet 5 matched 5.5 on 43 of 44. None of the flipped cases
  would have crossed the HIGH line (checked against each row's recorded score and bar).

## 2. Method and population

All runs on prod (`apollo-market`), real API, capture-once to `scripts/probes/_689/` (scripts + outputs).

- **Root-cause bisect:** the production containment prompt and schema, varied one factor at a time (8 variants),
  then the assignment prompt bisected sentence by sentence (`rootcause_s55.*`, `bisect_assign*.*`).
- **Refusal rate:** each production request captured from the real call site (DB writes and Telegram stubbed, the
  call stopped at the API boundary) and replayed 2–5 times on 5.5 (`rate_run.out`, `proto55*.out`).
- **EP theme-fit comparison — population:** every `mi_ep_theme_belonging_shadow` row with a non-empty shortlist and
  `fit_status` in (rejected, confirmed, window), one per (ticker, scan_date): **n = 44** (20 rejected, 1 confirmed,
  23 window), scan dates 2026-09-15 → 2026-09-29. Shortlist themes rebuilt from `mi_themes` as of each scan date;
  stock description from `get_descriptions_batch` (6 rows had none → the function's own "no description" failure,
  identical in every arm). Safeguard-blocked EPs are included — the shadow table records every scanned EP.
  Arms, each through the real `judge_theme_fit`: today's setup (Sonnet 5, scratchpad, thinking off) ×2; new setup
  on 5.5 ×2; new format on Sonnet 5 ×1.
- **Assignment:** 3 real batches of 12 from today's uncovered RS-leader pool against today's 122-theme board, through
  the real nightly `_propose_assignment_batch` (advisor allowed), old ×2 vs new ×2.
- **Discovery:** 2 batches of 20 uncovered leaders WITH descriptions (a first attempt without them was discarded — the
  function silently drops undescribed names), old ×2, new on 5.5 ×2, new format on Sonnet 5 ×1.

## 3. Root cause — what each variant did on 5.5

| Variant (containment prompt) | Result |
|---|---|
| original prompt + schema | refused, 0 output tokens |
| schema field description "Reason FIRST: …" → "Brief notes." | answered |
| field renamed, "Reason FIRST" text kept | refused (cut at 82 tokens) |
| child/parent wording swapped, reasoning text kept | refused |
| final "Fill analysis_scratchpad FIRST: …" paragraph removed | answered |
| thinking dropped / `between_tools` / effort low | refused in all three |

Assignment needed more than rewording: with the notes instruction reworded it still refused 4 of 5; with the
`analysis_scratchpad` field removed it answered 5 of 5. The identical prompt passed once and failed once in the
sentence bisect — the refusal is probabilistic, so single passes prove nothing.

## 4. EP theme-fit — old vs new (n = 44)

| Comparison | Agree |
|---|---|
| today's setup vs itself (noise floor) | 42 / 44 |
| new setup on 5.5 vs itself | 44 / 44 |
| today's setup vs new on 5.5 | 41 / 44 and 39 / 44 |
| new format on Sonnet 5 vs new on 5.5 | 43 / 44 |
| vs the stored live verdict (n = 21 judged) | today 18 / 21 · new 19 / 21 |

| Stock, scan date | Today's setup | New setup | Score, HIGH bar |
|---|---|---|---|
| MSTR 09-21 | rejected ×2 | Bitcoin Treasury & Crypto Proxy ×2 | 65.0 vs 65 (already at the line) |
| AKAM 09-25 | rejected ×2 (stored live: confirmed) | Cloud Application Delivery ×2 | 90.0 vs 65 (already HIGH) |
| BFLY 09-22 | rejected ×2 | AI-Driven Diagnostics & Imaging ×2 | 46.2 vs 65 (+10 → 56.2, stays below) |
| ABTC 09-18 | split 1–1 | Bitcoin Treasury & Crypto Proxy ×2 | 52.5 vs 65 (+10 → 62.5, stays below) |
| CBRL 09-23 | split 1–1 (stored live: rejected) | Restaurant Chain Recovery ×2 | 52.5 vs 65 (+10 → 62.5, stays below) |

Fit-check latency: new p50 2.0 s, max 5.0 s; today p50 2.9 s, max 6.0 s — inside the 15 s fit timeout.

## 5. Assignment and discovery

| Batch | Today's setup (×2) | New on 5.5 (×2) |
|---|---|---|
| assignment 1 | PUBM → Digital Advertising · none | PUBM → Digital Advertising (both) |
| assignment 2 | ODD → DTC Health & Wellness · none | USPH → Post-Acute & Home Healthcare (both) |
| assignment 3 | PAYC → Enterprise HR SaaS (both) | PAYC → Enterprise HR SaaS (both) |
| discovery 1 | ad-tech APPS/PUBM + EM telecom IDT/VEON (both) | ad-tech APPS/PUBM only; declined IDT/VEON "different telecom models" (both) |
| discovery 2 | AVT/CNXN + UFPT/WST (both) | AVT/CNXN + UFPT/WST (both) |

The new format on Sonnet 5 reproduced today's discovery exactly (both batches) — the prompt change is neutral for
discovery; 5.5 itself is slightly stricter on a two-stock pair. The `declined` reasons are specific (e.g.
"PAYC: belongs to existing HR SaaS theme").

## 6. What this does not answer

- **Confirmations are thin:** 1 of the 21 judged EP cases was a live confirmation. The new setup's extra confirms are
  listed for him to read; they are not graded here.
- **Refusal at a low rate is not ruled out.** 2–5 runs per job cannot see a refusal rate under ~10%; the first nights
  on 5.5 measure it (the EXPECT below).
- **One day's board and pool** for assignment and discovery; nightly content varies.
- **Nightly cost of thinking** is not measured; the ceilings were doubled to leave thinking room.
- Whether the extra theme boosts improve EP selection is a returns question this does not touch.
