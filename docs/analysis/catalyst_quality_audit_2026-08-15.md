# Catalyst grading audit — "game changer, not expected that explains the gap"

Operator, 2026-08-15: *"the catalyst needs to be game changer, not expected that explains the gap,
we have so many EPs that have avg catalyst, there's so much you're not looking into."*

Read of `mi_ep_alerts`, prod 2026-08-15. **Measurement only — grading is a detection criterion
(THE LINE).**

## 1. The label is not the problem people assume; the AXIS is missing

Over the last 120 days: `game_changer` = **96 of 403 alerts (24%)**. (The often-quoted 59% is the
60-day earnings-window figure — the label inflates seasonally, it is not permanently at 59%.)

The rationales behind recent `game_changer` grades are genuinely substantive:

| Ticker | Date | Type | What earned the grade |
|---|---|---|---|
| VERA | 08-14 | policy | FDA accelerated approval + commercial launch of a first-and-only drug |
| CGEM | 08-13 | policy | Pivotal Phase 3 met its primary PFS endpoint |
| RIOT | 08-11 | sales_acceleration | 20-year, 191 MW data-centre lease with a frontier AI lab, ~$9.1B |
| EROC | 08-12 | sales_acceleration | 10× YoY backlog surge to ~$1.7B, >50% of market cap; new 470 MW order |
| ETON | 08-14 | sales_acceleration | Record Q2 product sales $37.6M, +99% YoY |
| HLIT | 08-13 | sales_acceleration | Broadband revenue +54% YoY, backlog/deferred +71% |
| HTFL | 08-14 | sales_acceleration | Q2 revenue $64.1M (+48% YoY) with a full-year guidance raise |
| ATRO | 08-12 | sales_acceleration | Record sales +27.0% YoY |
| **GLBE** | 08-12 | sales_acceleration | **Revenue BEAT ($299M vs $283.1M) plus an FY raise** |

🔴 **His point lands exactly at the bottom of that list.** An FDA approval, a $9.1B lease and a 10×
backlog surge are NEW FACTS that change the forward model. A **$16M revenue beat against an
estimate**, or "record sales +27% YoY", is a **good quarter reported on schedule** — the market had
an estimate, the date was known, and nothing about the company's trajectory changed. **Both are
graded `game_changer`, both score the same 25 points, and both trip the conviction floor into
HIGH.**

## 2. What we do NOT capture — and this is the specifiable gap

`catalyst_type` exists (`sales_acceleration`, `policy`, `theme`, `new_product`,
`pre_catalyst_anticipation`, `other`, `unknown`) but there is **no EXPECTEDNESS axis anywhere**:

- **Scheduled vs unscheduled.** An earnings release is a diarised event; an 8-K disclosing an
  approval or a contract is not. We already read the 8-K/EX-99.1 and its item number, and we have
  an earnings calendar — so this is derivable today, not new capture.
- **Backward-looking vs forward-changing.** "Q2 revenue was X" reports a closed period.
  "20-year lease worth $9.1B" / "FDA approval" / "10× backlog" changes future revenue. Distinct
  from magnitude.
- **Beat-vs-estimate vs growth-vs-history.** ⚠ This is his NBIS complaint verbatim (08-12,
  `operator_shared_notes.md`): *beat-vs-expectation is not growth* — NBIS graded "moderate" on a
  marginal beat while revenue grew >400%. GLBE is the mirror image: graded top on a beat.

## 3. Also measured: over half the alerts carry NO catalyst type at all

`catalyst_type` is NULL on **224 of 403 alerts (56%)** in the window — and **25 of those NULLs are
still graded `game_changer`**. So a quarter of top-grade alerts got the top label with no typed
catalyst behind it. Whatever the grade means there, it is not a classification.

## 4. What follows (FORKS — none pre-decided; grading is his)

1. Add an **expectedness axis** (scheduled/unscheduled · backward/forward · beat-vs-estimate
   distinct from growth-vs-history) and require it for `game_changer`, so a good quarter cannot
   earn the same label as a new fact.
2. Split the label rather than re-weight it: `game_changer` reserved for forward-changing
   unscheduled facts; a separate grade for strong scheduled results.
3. Require a non-NULL `catalyst_type` before any `game_changer` grade.
4. Leave the label and stop letting it drive the conviction floor (§the grade mechanism read).

▶ Each is a detection-criterion change: CHANGE_PROCESS + N≥10 backtest + his sign-off.
▶ The $0 evidence that would rank them: label each of the 96 `game_changer` alerts scheduled vs
unscheduled from the 8-K item + earnings calendar we already store, then compare forward outcomes.
