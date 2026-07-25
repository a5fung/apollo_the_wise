# HTF deal-pin leak — ATAI 2026-07-24 (diagnosis + CHANGE_PROCESS proposal)

**Status: PROPOSAL — NOT SHIPPED.** Needs operator sign-off (detection criterion → THE LINE) and the
filter-list judgment call required by `CHANGE_PROCESS.md` rule 3.
**SSoT to amend in the same commit: `docs/setups/htf.md`** (HTF phase = *shadow, telemetry-only, no
order fires* — this change touches no money path).

**Trigger**: operator, 2026-07-24 — the nightly HTF digest surfaced `ATAI — base 5d · runup +97% ·
range 1.00 · vol 1.00` as the single 🌀 COILED actionable setup. Operator: *"ATAI is a buyout so the
HTF is invalid."*

---

## 1. What ATAI actually is

`mi_daily_closes`, ATAI:

| date | open | high | low | close | volume | range % |
|---|---|---|---|---|---|---|
| 07-15 | 5.75 | 5.76 | 5.30 | 5.36 | 6.1M | 8.58 |
| **07-16** | 7.065 | 7.22 | 7.02 | 7.15 | **165.6M** | 2.80 |
| 07-17 | 7.085 | 7.22 | 7.08 | 7.22 | 41.8M | 1.94 |
| 07-20 | 7.16 | 7.21 | 7.10 | 7.19 | 22.3M | 1.53 |
| 07-21 | 7.165 | 7.21 | 7.13 | 7.135 | 13.8M | 1.12 |
| 07-22 | 7.15 | 7.19 | 7.14 | 7.18 | 11.0M | 0.70 |
| 07-23 | 7.16 | 7.20 | 7.15 | 7.17 | 9.0M | 0.70 |
| 07-24 | 7.17 | 7.19 | 7.16 | 7.18 | 7.0M | 0.41 |

A 20× volume event on 07-16, then price welded inside a **1.5% band** for six sessions, range decaying
2.80 → 0.41% and volume bleeding 165M → 7M. That is a cash-deal pin — and, by pure price mechanics,
also a textbook coil. **The tightness that scored it COILED *is* the pin.**

## 2. Why both existing M&A layers missed it

`flag_detector.py:1102` (news) and `:1136` (deal-pin backstop) both run on COILED/TRIGGERED.

**Layer 1 — Polygon news.** Live test against prod, 21d lookback:

```
polygon items returned: 2
  2026-07-16 | title_kw=None | desc_kw=None | Why AtaiBeckley Stock Soared Today
  2026-07-06 | title_kw=None | desc_kw=None | AtaiBeckley Doses Last Patient in VLS-01 Phase 2b ...
polygon_news_has_mna_headline: None
```

Two articles in three weeks, neither carrying an M&A keyword. Nothing to match. **The #416 guards
(A/B/C) are NOT implicated** — no keyword ever matched, so no guard vetoed anything.

**Layer 2 — deal-pin backstop.** Requires median (H−L)/C over the last **10** sessions < 0.5% AND ≥5
sub-0.5% sessions. ATAI on 07-24: median **1.735%**, sub-0.5% days **1**. Fails both.

Structural, not a tuning miss: a 6-session-old deal cannot fill a 10-session window — the window still
holds the pre-announcement volatility (07-14 range 14.11%).

## 3. The backstop only catches *mature* pins — measured

Every `deal_pin_signature` firing in the table's lifetime: **5 rows, 2 tickers** (KALV, ASRT).

KALV — the case the backstop was built for:

| dates | outcome |
|---|---|
| 05-06 → 05-11 | **COILED, leaked to the operator (4 sessions)** |
| 05-12 → 05-25 | caught by `mna_filter:polygon_news` (news finally appeared) |
| 06-04 → 06-08 | caught by `deal_pin_signature` — **~29 days after the first leak** |

Four further pin-tier tickers leaked as actionable COILED and were **never** caught by either layer:
AVNS (05-04), CCRN (05-14/15), PAYO (06-23/24/25), ATAI (07-23/24).

## 4. Axis 1 — 5-session price band

Across **all 405** historical COILED/TRIGGERED rows.
`band_pct = (max high − min low) / avg close` over the last 5 sessions.

Distribution: min 0.32 · p05 4.64 · p25 9.08 · **median 11.75** · ≤3%: **12 rows** · ≤4%: 18 · ≤5%: 24.

The 12 rows at ≤3% (5 tickers), then the first rows above:

| ticker | scan_date | band % | 20d fwd close-spread |
|---|---|---|---|
| AVNS | 05-04 | 0.32 | 1.79% |
| CCRN | 05-15 / 05-14 | 0.46 / 0.91 | 1.07% |
| KALV | 05-11 / 05-06 / 05-07 / 05-08 | 0.69 / 0.81 ×3 | 0.90% |
| PAYO | 06-23 / 06-24 / 06-25 | 0.85 / 1.56 / 1.85 | 1.28% |
| **ATAI** | **07-24 / 07-23** | **1.53 / 1.95** | 0.14% (2 bars) |
| — gap — | | | |
| HUM | 05-28 / 05-29 | 3.07 / 3.18 | **+25.68%** (308.70 → 383.84) |
| SXT | 05-12 | 3.65 | 7.18% |

⚠ **Caveat — the forward-drift column is partly circular.** "Tight 5-day band → tight 20-day band" is
substantially autocorrelation. HUM is the only genuine counterexample and it sits just 1.1pp above the
cut. On this axis alone the threshold rests on N=1 either side of the boundary. That is why axis 2
matters.

## 5. Axis 2 — the volume event (what makes this signable)

A deal pin is causally *announcement → weld*; a quiet coil has no such event. Measured as
`max volume over last 10 sessions / avg volume over sessions 11–40`:

| ticker | band % | vol spike |
|---|---|---|
| KALV | 0.69–0.81 | **61×** |
| PAYO | 0.85 / 1.56 / 1.85 | 19.2 / 13.6 / 12.6× |
| ATAI | 1.53 / 1.95 | **19.0 / 19.2×** |
| CCRN | 0.46 / 0.91 | 17.2 / 16.5× |
| AVNS | 0.32 | 1.4× ← *see below* |
| — | | |
| HUM | 3.07 / 3.18 | **1.0 / 1.0×** |
| SXT | 3.65 / 3.70 / 3.88 | 2.9 / 1.1 / 2.9× |
| GEO, HNGE, DGII, EFXT, SNEX, RVMD | 3.9–5.7 | 0.8–2.2× |

**Every fresh pin ≥12.6×. Every non-pin row in the top-30-by-band ≤2.9×.** A ~4× margin on an axis
independent of the band — far wider than the band's own 1.95/3.07 gap.

**AVNS at 1.4× is the informative exception**, and it confirms the division of labor. AVNS's
going-private deal was announced **4/14** (independently corroborated in-repo — `ep_detector.py:1290`:
*"AVNS 5/4: Perplexity returned 'no specific news' for 4/14 going-private; Polygon had the headline the
whole time"*). By the 05-04 COILED the announcement had aged out of the 10-session window. AVNS is a
*mature* pin — the existing rule's job, not this one's.

## 6. The path I tested and rejected

The obvious fix — let the flag path reuse the EP Claude-classifier verdict (`catalyst_quality='mna'`,
which fired on ATAI 07-16) — **does not survive contact with the data. Do not ship it.**

1. The verdict is not in `mi_ep_alerts` (the filter suppresses *before* the alert row is written). It
   lives only in `mi_audit_log`. Joining flag rows to that store within 21d yields 3 rows / 2 tickers:
   ATAI **and ACLS**.
2. ACLS's stored verdict is junk: `catalyst_quality='mna'` while its own `news_summary` reads *"No
   recent news or catalysts found for ACLS (Axcelis Technologies)"*, and a second event's summary
   describes a **different company** (MRBK earnings) — multi-ticker news bleed. ACLS then ran
   $164 → $191. Suppressing it would have been a real miss.
3. Passing the stored text so the guards run does not help. Measured on prod:

   ```
   ATAI  : matches_mna_keywords=None  is_likely_ma(q=mna,+texts) = (True, claude_classifier)
   ACLS#1: matches_mna_keywords=None  is_likely_ma(q=mna,+texts) = (True, claude_classifier)
   ACLS#2: matches_mna_keywords=None  is_likely_ma(q=mna,+texts) = (True, claude_classifier)
   ```

   `matches_mna_keywords` returns `None` even for ATAI — *"speculation about strategic/M&A activity"*
   is not in the keyword list. Corroborating the label against its own evidence text would veto ATAI
   too, and the guards cannot separate the true verdict from the junk one. **Classifier-verdict sharing
   is 1-true / 1-junk at ticker level on the only sample that exists.**

**Guard-C check (verified, no action needed):** `is_likely_ma` short-circuits on
`catalyst_quality=='mna'` guarded only by `text_implies_acquirer_or_completed(catalyst_texts or [])` —
which returns False on an empty list, making Guard C vacuous for any caller passing `catalyst_quality`
without texts. Confirmed safe in production: `ep_detector.py:1312` is the only such caller and it does
pass `catalyst_texts`. Worth a docstring note so a future caller can't reintroduce it; not a defect
today.

## 7. Proposed change (needs sign-off)

**Not a new lever — a re-specification of the existing deal-pin backstop** so it can fire on a *fresh*
pin, as a two-axis conjunction:

> Over the last 5 sessions `(max high − min low) / avg close ≤ 2.5%`
> **AND** `max volume over last 10 sessions / avg volume over sessions 11–40 ≥ 5×`
> → stage → `unqualified`, `reason = 'mna_filter:deal_pin_fresh'`.

Keep the existing 10-session rule unchanged for mature pins. Additive — nothing currently caught is
lost; the two rules cover complementary ages of the same phenomenon.

**Evidence**: 405-row historical replay, **window 2026-05-04 → 07-24, 89 distinct tickers**. Affects
**11 rows / 4 tickers** (ATAI, KALV, CCRN, PAYO); preserves 394 rows including HUM (+25.7%) and SXT
(+7.2%). N=11 ≥ 10 per discipline rule 1.
⚠ **Single-regime limitation**: that window is one regime. Per #454's finding that the kill/scale
envelope was silently bull-conditional, this calibration carries the same caveat and should be re-cut
at the quarterly band review.

**Threshold robustness**: because both gaps are wide, band ∈ {2.0, 2.5, 3.0} and spike ∈ {5×, 10×} all
select the same 11 rows. The choice is not load-bearing — which is the main argument for the
conjunction over either axis alone.

**Anticipated effect**: ~11 actionable COILED rows suppressed per ~3 months (of 405). ATAI drops off
the board. KALV would have been caught 05-06 instead of 06-04; CCRN and PAYO caught at their first
actionable row instead of never.

**Self-healing** (an advantage over the rejected stored-verdict path): if the ATAI deal breaks, the
band widens and suppression stops on its own. No TTL, no new persistent ban surface — which the
`mi_theme_exclusions` scar says to avoid.

**Reversion-flag**: REFINEMENT of the 2026-05-11 deal-pin-signature change — same intent (catch
zero-news M&A targets by price signature); the prior statistic is correct for mature pins and simply
has no reach on fresh ones. Not a reversal: nothing the prior rule catches is given up.

**Scope**: `flag_detector.py` only. HTF is shadow/no-money. Extending to EP/9M would change detection
on money paths — deliberately **out of scope**, and would need its own sign-off and FN number.

### ⚖ Operator judgment required (CHANGE_PROCESS rule 3)

Rule 3 forbids me classifying the filter list. The 11 rows in §4/§5 are the complete list that would be
suppressed. What I can state as fact: all four tickers' prices stayed inside ~1.3% for the following 20
sessions, and each had a 12–61× volume event preceding the weld. Whether that makes them
correctly-filtered M&A targets is **your call**, not mine.

Open forks:
1. **Sign the conjunction as specified?** (band ≤2.5% AND spike ≥5×, flag-only.)
2. **AVNS-class mature pins** stay with the existing 10-session rule, which has fired only 5 times
   ever and missed AVNS/CCRN/PAYO. Tighten that separately, or leave it?
3. **The two existing COILED rows** for ATAI (07-23, 07-24) remain in `mi_flag_candidates`. Correcting
   them is a prod data mutation — naming it rather than folding it in silently.

## 8. Verification plan

- **$0, pre-deploy**: replay the flag M&A stage for ATAI at `scan_date=2026-07-24`; confirm the stage
  flips to `unqualified` / `mna_filter:deal_pin_fresh`, and that HUM 05-28 does **not** flip.
- **Verify-live**: the next nightly HTF digest (17:25 ET scan) does **not** list ATAI as COILED — the
  rendered Telegram digest, not the DB row. [[verify-operator-facing-surface]]

## 9. Doc gap noted

`docs/setups/htf.md` documents the geometry gates but **not** the two M&A layers that run on
COILED/TRIGGERED. They live only in `flag_detector.py`. The change-log entry for this proposal should
also backfill the existing layers into the SSoT.

## 10. Reproduce

All queries are read-only SELECTs against prod `mi_flag_candidates` / `mi_daily_closes` /
`mi_audit_log`; the band + conjunction SQL is reproduced inline in §4–§5.
