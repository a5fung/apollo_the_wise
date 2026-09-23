# #416 — M&A false-positive filter amendment (DRAFT PROPOSAL for operator sign-off)

**Status: DRAFT — the operator signs; the agent does not touch the filter (THE LINE).**
This is a detection-criterion + entry-discipline change (it changes which EP/9M alerts the
M&A filter suppresses → which entries can occur). Deliverable = this proposal. No code changed.

Charter: #416 (due 7/16), sitting-ratified PROCEED (7/4 Tier-2). Composes with #410's pin-guard
and the M&A-filter direction-blindness finding.

---

## 1. What the filter does (so the tradeoff is legible)

`ma_filter.is_likely_ma()` is a **suppressor**: when it fires on a would-be EP/9M candidate,
the detector drops the alert on the theory that a stock **pinned by a definitive deal-to-be-
acquired** has no momentum left to trade. It fires from three sources, cheap→expensive:

1. **`claude_classifier`** — `catalyst_quality == 'mna'` (Claude's catalyst verdict; EP only).
2. **`keyword_in_text_{idx}`** — a raw M&A keyword substring in catalyst prose (Claude analysis,
   news_summary, …). `_MNA_KEYWORDS` = buyout/takeover/merger/definitive agreement/tender
   offer/going private/… (17 terms).
3. **`polygon_news`** — M&A keyword in a Polygon headline. Path A = title match (+ `_ticker_is_
   acquirer` / `title_implies_acquirer` guards). Path B = description match gated by the ticker's
   Polygon-insights `sentiment_reasoning` also containing an M&A keyword.

**The asymmetry that frames every decision below.** A **false positive** (firing on a
non-binding/mislabeled catalyst) = a **missed momentum winner** (FRMI +25%, IMAX's sale-pop ran).
A **false negative** (failing to suppress a genuinely pinned name) = usually a break-even
time-stop dud — **but with a tail**: a *deal-break* on a name we entered can gap down and jump
the stop. So loosening the filter is **not free**; it trades a confirmed missed-winner class for
a small, tailed dud risk. **This tradeoff is the operator's to weigh — this doc does not decide it.**

---

## 2. The three ratified false-positives are three different failures on three different paths

Full `mi_audit_log.mna_filter_fired` rows pulled from prod (2026-07-12). Sitting-ratified labels
(7/4) in **bold**; agent-assessed cases marked as such (kept distinct per CHANGE_PROCESS gate #4).

| FP | Path | The matched text | Why it's wrong |
|---|---|---|---|
| **MMED** (+23%, FP) | `keyword_in_text_1` | matched **"takeover"** inside *"…company-specific execution news … **not a single dramatic takeover** or earnings shock…"* | **Negated keyword.** The prose says it is NOT a takeover; the substring match is context-blind. |
| **FRMI** (+25%, FP) | `polygon_news` Path B | matched **"merger"** in insight_reasoning *"…gained 22.6% on **proxy campaign** announcement seeking **strategic alternatives** and board changes…"* | **Exploration / activist agitation, non-binding.** A proxy fight for "strategic alternatives" is a bullish *hope* catalyst, not a signed deal — the opposite of a price-pin. |
| **ONDS** (+23%, FP) | `claude_classifier` | `catalyst_quality='mna'` on *"…the **Mistral acquisition closing**, which gave Ondas direct prime-contract…"* | **Direction-blindness.** ONDS is the **acquirer** — it *bought* Mistral (a bullish growth catalyst). The filter is meant to suppress *targets*, not buyers. The polygon path guards this (`_ticker_is_acquirer`); the classifier path does **not**. |

**The confirmed true-positive that any fix must preserve:** **SUNE** (ratified TP) fired via
`polygon_news` on *"…announcement of **definitive reverse merger with Suniva**…"* — the operator
chose to suppress it on methodology (a reverse-merger microcap at $2.83 is not the clean EP setup,
even though it popped). Note SUNE is the *surviving* entity of the reverse merger, so a naive
"suppress only when ticker is the target" rule would **un-suppress SUNE and break the ratified TP.**
The fixes below are therefore **context guards, not a direction-only rule.**

---

## 3. Mechanism choice — blacklist (targeted guards), decided by data not preference

The advisor flagged the real fork: **whitelist** ("fire only when binding-deal language present")
vs **blacklist** ("keep firing broadly; reject the identified non-binding contexts"). Measured on
prod (896 fires):

| Path | fires | carry explicit binding language ("definitive/to be acquired/agreement to acquire/completed acquisition") |
|---|---|---|
| polygon_news | 495 | **1** |
| claude_classifier | 205 | **1** |
| keyword_in_text_0/1 | 127 | **3** |

A whitelist would flip **~890 of 896** fires to not-fire and **gut the filter** — most genuine M&A
suppress correctly via *buyout / tender offer / going private / acquired-by*, which are binding but
never contain the word "definitive." **→ Whitelist rejected. Blacklist adopted.** Keep the broad
fire; add three narrow reject-guards. Measured blast radius of the blacklist = **6 events total**
across all 896 (§4) — surgical.

---

## 4. Proposed guards (one per mechanism) + the backtest

Root principle shared by all three: **suppress a candidate only when the M&A signal is a *binding
deal that pins THIS ticker as the target*** — reject *negation*, *exploration/speculation*, and
*acquirer-side* contexts.

### Guard A — negation/speculation guard on the keyword path (`keyword_in_text`)
Before accepting a keyword match in **prose** (news_summary / Claude analysis), reject if the
match sits in a non-binding window: a negator within ~20 chars before it (`not`, `no`, `n't`,
`without`, `rather than`, `unlike`, `denies/denied`) **or** a speculation marker within ±40 chars
(`speculation`, `rumor`, `reportedly`, `potential`, `exploring`, `talks`, `considering`) with no
binding marker in the same sentence. (Reference impl: a shared `mna_context_is_binding(text, pos)`
predicate; exact word-lists are the operator's to ratify.)

### Guard B — exploration-reject guard on polygon Path B (`insight_reasoning`)
**Pure blacklist (same shape as Guard A — not a require-binding whitelist).** When Path B matches
an M&A keyword in the ticker's `sentiment_reasoning`, **reject** the fire when exploration/agitation
markers dominate the reasoning (`strategic alternatives`, `proxy campaign`, `activist`,
`exploring options`, `seeking`) **and** no signed-deal marker is present. The signed-deal marker
(`definitive`, `agreed to`, `to be acquired`, `completed`) is the **escape from the reject**, NOT
a firing requirement — a plain "XYZ in merger talks" fire with no exploration marker is left
untouched. FRMI dies (proxy-campaign/strategic-alternatives, no signed-deal marker); SUNE lives
(carries "definitive"). Framing it as "require binding language" instead would recur the §3
whitelist trap inside Path B (FRMI matched "merger", so a literal require-form fixes nothing; a
narrow binding vocabulary would start rejecting a chunk of the **495** polygon fires). Reuses the
same `mna_context_is_binding` predicate as the reject-escape.

### Guard C — acquirer-side / completed-deal guard on the classifier path (`claude_classifier`)
**Port the polygon path's existing acquirer heuristic** (`_ticker_is_acquirer` /
`title_implies_acquirer`) to gate the `catalyst_quality == 'mna'` verdict: if the catalyst text
frames THIS ticker as the buyer (*"<Company> acquisition closing"*, *"acquired X for $Y"*,
*"prime-contract"* growth framing), do not suppress. ONDS is rejected — and note it is
*"acquisition **closing**"*: a **completed** deal, not merely acquirer-side. A closed deal pins
*neither* party (the pin is on the target's shares *pre-close*, at the agreed price; post-close the
target's ticker is gone and the acquirer trades on the combined fundamentals) — the more general
reason the suppression is wrong here. This is the surgical, deterministic, testable form of the
direction-blindness fix; the deeper option (teach the classifier prompt acquirer/target
directionality) is noted as a follow-on, not bundled.

### Backtest (blacklist blast radius over all 896 fires, prod 2026-07-12)
Every fire whose stored text is negation- / exploration- / acquirer-flavored — the guards' entire
reach:

| Ticker | Path | In a guard's scope? | Assessed | Flip |
|---|---|---|---|---|
| **MMED** | keyword_in_text_1 | A | **ratified FP** | suppress→pass ✓ correction |
| **FRMI** | polygon Path B | B | **ratified FP** | suppress→pass ✓ correction |
| **ONDS** | claude_classifier | C | **ratified FP** | suppress→pass ✓ correction |
| IMAX ×2 | keyword_in_text_1 | A | agent-assessed FP ("potential sale… 'takeout' speculation"; ran) — *operator to confirm* | suppress→pass (correction if confirmed) |
| D (Dominion) | claude_classifier | (C-adjacent: "strategic review") | agent-assessed — *operator to confirm* | flips only if Guard C's exploration arm extends to classifier |
| PZZA | claude_classifier | (exploration: "takeover speculation… reportedly made a bid") | agent-assessed — *operator to confirm* | same |

**Result:** the guards flip **all 3 ratified FPs (MMED, FRMI, ONDS)** and up to 3 agent-assessed
FPs (IMAX/D/PZZA, pending operator confirmation) — **and zero *known* TPs.** SUNE is preserved
(binding "definitive" language; polygon acquirer-guard already passed it). The broad ~890
suppressions (the filter's real work) are untouched by these markers.

**Limits of this backtest (read before trusting the numbers):**
1. **Truncation → lower bound.** The scan is `ILIKE` over `mi_audit_log.detail`, stored truncated
   at ~500 chars. A trigger phrase past char 500 is invisible, so the 6-event reach is a
   **lower bound** — and for a suppress-*relaxing* change, understating the blast radius understates
   **FN exposure**, the direction that matters. Read "≤6 / ~0.7%" as an *approximate lower bound*, not a measurement.
2. **Proxy ≠ predicate.** "Marker phrase present in `detail`" is not the windowed guard logic
   (negator-within-20-chars, exploration-dominant-and-no-escape). Error runs both ways; the ILIKE
   scan only *approximates* what the ratified guards would do.
3. **"0 TPs" = "0 *known* TPs."** There is exactly **1** confirmed TP (SUNE, safely outside the
   scan) against an otherwise-**unlabeled** 896. Broader TP-safety is *unmeasured*, not proven zero.

FN risk introduced = the tailed case in §1: a genuinely binding deal described *only* with
negation/speculation/acquirer framing and no signed-deal escape — **none surfaced in the (truncated)
896**, but non-zero forward. This is the tradeoff the operator weighs. On **N≥10 (CHANGE_PROCESS):**
the FP population *is* small (≤6 in reach) — N is bounded by reality here, and because the change is
suppress-*relaxing*, what the evidence actually bounds is **FN exposure**, not the FP fix; the
precise offline simulation (§5) is the honest N-gate, run once the word-lists are ratified.

---

## 5. CHANGE_PROCESS change-log fields (for the operator's sign-off entry)

**Trigger:** 7/4 Tier-2 sitting ratified 3 M&A-filter false-positives (FRMI, ONDS, MMED) that
suppressed real momentum runners; #416 chartered the amendment.

**Evidence:** 896 historical `mna_filter_fired` rows (prod). Three FPs root-caused to three
distinct path/mechanisms (§2). Blacklist blast radius = 6 events; flips all 3 ratified FPs, 0
confirmed TPs, SUNE (ratified TP) preserved (§4). Whitelist rejected on a measured 890/896 FN-surface (§3).

**Anticipated effect:** suppression rate falls marginally (≤6 of 896 historical fires; ~0.7%).
Expect a small number of previously-suppressed EP/9M candidates to become eligible again — those
in negated/exploration/acquirer-side contexts. No change to fires carrying genuine deal language.

**Reversion-flag:** REFINEMENT of the #410 pin-guard / polygon Path-B logic (tightening the fire
condition in the accuracy direction #410 intended). Guard A and Guard C are NEW (no prior
negation-guard on the keyword path; no prior acquirer-guard on the classifier path).

**Status: SIGNED 7/12 eve** (rulings-pack R6, all three §6 forks: IMAX confirmed FP · Guard-C =
the surgical port · FN tail accepted as priced). **N-gate sim RUN 7/12 eve** (full-text, real
guard predicates, prod): 896 rows → 862 parsed (34 unparseable; 9 truncated-at-write) →
**7 flips / 5 distinct**: MMED (guard-A negated ✓ ratified), ONDS ×2 (guard-C acquirer/completed
✓ ratified), IMAX ×2 (guard-A speculation ✓ operator-confirmed), **+2 NEW the ILIKE proxy missed:
WEN 5/12 + IMVT 5/20** (both guard-A speculation-window — eyeball at build time). ⚠ OPEN
VERIFICATION: **FRMI did not flip** — expected via guard-B; likely among the 34 unparseable
(truncated-at-write JSON kills `json.loads`). VERIFY at build: if FRMI's row is write-truncated,
the *live* guard sees the full text (it runs pre-write) so the guard still works — but the sim
must re-run FRMI's inputs manually to prove guard-B's word-list catches it BEFORE shipping.
Blast radius confirmed surgical: ~0.8% of fires (a FLOOR — truncation under-counts).
**PRE-DEPLOY GATE — SHIPPED-CODE REPLAY (advisor 7/13): PASS.** Ran the VERBATIM shipped guard block (`ma_filter.py`) over all 896 rows: 9 flips / **5 distinct tickers (IMAX, IMVT, MMED, WEN, ONDS) — the SAME set the sim's inline regexes found**, so bare `could` did NOT broaden the flip set. All 3 sitting-ratified FPs flip (MMED guard-A · ONDS guard-C · IMAX guard-A); FRMI is truncated-at-write so the corpus can't parse it (proven separately on full text). **SUNE (the TP) did NOT flip.** The 2 non-ratified extras classified (to the available text depth; both were in the signed sim evidence): WEN = Trian 'eyeing a take-private' (speculation, not signed) · IMVT = 'clinical/pipeline catalysts plus rising speculation' (incidental keyword) — NEITHER a binding price-pin → no false-negative injection. Evidence matches the shipped code. Build steps (this week, due 7/16):
1. **Precise offline corpus simulation (the real N-gate, pre-deploy).** A throwaway read-only
   script queries the **full** `detail` (not truncated) for every `mna_filter_fired`, runs the
   *ratified* guard predicate (not the ILIKE proxy), and reports the exact flip list + a
   hand-labelled sample of the flips. This replaces the §4 lower-bound scan with a measured
   blast radius before any code ships. (Read-only analysis — permitted pre-sign-off if the
   operator wants the number first.)
2. Implement Guards A/B/C behind the shared `mna_context_is_binding` predicate.
3. Regression cases: MMED/FRMI/ONDS reject; SUNE **and** a plain "acquired by X" / "in merger
   talks" case still fire (guards must not gut the broad suppression).
4. Land the change-log entry in `docs/setups/catalyst_rubric.md`; deploy market-agent;
   verify-live on the next fire of each path.

---

## 6. The forks the operator rules

1. **Confirm the agent-assessed FPs** (IMAX / D / PZZA) — FP or not? (Sets whether Guard A's
   speculation arm and a Guard-C exploration arm are in scope, or just the 3 ratified fixes.)
2. **Guard C depth:** the surgical port of the polygon acquirer-heuristic (recommended — mirrors
   an existing, tested mechanism) vs teaching the classifier prompt directionality (deeper; own task).
3. **The FP/FN asymmetry (§1):** accept the small tailed FN risk to recover the missed-winner
   class? (The reason to say yes: the filter is a *suppressor*; its errors cost winners. The reason
   for care: a deal-break tail. Operator's call.)
