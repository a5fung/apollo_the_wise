# EPs the operator named himself

**The single list. Every stock he has personally called a real EP — nothing inferred, nothing
screened in, nothing added because it made money.** Created 2026-09-05 on his instruction
(*"if not already, maintain a single list of EP directly from me so easy to find and reference"*),
after BFLY turned out to have been labelled on 2026-06-19 and sat unfiled for eleven weeks.

**This is the ground truth for every "does our selection work" question.** Return-selected cohorts
are not — he ruled that out explicitly: the goal is finding real EPs, and our own exit corrupts any
P&L-based label (TEAM is the proof — we lost on it, the stock went +72%).

## The rule for adding one

He names them in passing, one sentence, usually mid-conversation about something else. **Three of
the six below arrived in a single afternoon that way.** When he calls a stock an EP:

1. Add it to `tests/fixtures/must_not_miss_eps.py` with `label_source="operator"` and his words.
2. Add a row here. `tests/test_operator_labelled_ep_list.py` fails the build if the two disagree.
3. Record what our system actually did with it — that is the whole point of the list.

Never add a name because it worked. Never remove one because it didn't.

## The list

| Ticker | EP date | Gap | What he said | What our system did |
|---|---|---|---|---|
| **BFLY** | 2026-06-18 | 26.3% | *"BFLY 6/18 **IS** an Episodic Pivot — `routine` is the WRONG grade."* | ❌ **Downgraded** `strong`→`routine`, reason `news_corpus_sparse_no_q_rev`. Partnership catalyst, so no revenue line to extract — downgraded for missing data it could never have had. Stock 5.71 → 8.90 (+55.9%) → 9.00 two months on. |
| **ABNB** | 2026-08-07 | 8.6% | *"ABNB didn't make as EP alert on 8/07 but looking at it now it looks like a potential real EP to me"* | ❌ **Never scored — cut by the top-20 shortlist.** Gapped 8.6% at the open, **under our 9% floor by 0.4pp**; cleared it intraday and we re-checked every 5 min, but its only two scan rows (09:50, 09:55, gaps 12.6%/14.2%) were both dropped as *outside top-20 gap cap* — 20+ names gapped harder. Closed +17.4% on 2.8× volume and held 184–185 a week later. 09:50 is also past the 09:44 order window. |
| **PLTR** | 2026-08-04 | 15.5% | *"pltr another one"* | ✅ **Everything worked.** Rubric passed it, 96 / HIGH / game_changer; traded it, stop trailed to 170.47 above a 149.05 entry. The only end-to-end success on this list. |
| **TEAM** | 2026-08-07 | 31.7% | *"i got into TEAM as EP after apollo was stopped out, it's still working after weeks and qualify as EP in my book"* | ⚠️ **Found it, bought it, lost on it.** Scored 115.2 / HIGH and alerted. We entered 147.13 and stopped out 143.21 the same day under the old ORB-low stop; the stock reached 189.58. Under today's `entry − 2R` stop it holds by $2.22 and the runner is still open. |
| **HTFL** | 2026-08-14 | 26.0% | *"i'd say htfl is another recent one"* | ⚠️ **Selection worked, entry refused it.** 96 / HIGH / game_changer, then skipped: `setup:stop_too_wide` (ORB range $2.55 = 7.0% vs 1.5×ATR $2.19). Stock 31.01 → 48.91. |
| **MRNA** | 2026-08-19 | 84.3% | *"MRNA is a textbook EP... the news is truly gamechanging, the move, etc. is textbook."* | ✅ **Caught**, 115.2 / HIGH. Full write-up: `docs/methodology/ep_reference_mrna_2026-08-19.md`. |
| **CHPT** | 2026-09-03 | 33.0% | *"a perfect EP type with news catalyst, and ORB 1min high entry worked, also it closed with the highest volume ever"* | ❌ **Never scored** — `filter:mcap_too_small: $134M`, rejected before anything looked at it. Prompted the low-cap lane (#624). |

## What the list says, as of 2026-09-05

- **Seven names. One clean success (PLTR).**
- **Nothing on this list failed in selection *scoring*.** Of the four the scorer saw, all four graded HIGH.
- **The five that went wrong each failed somewhere different:** the catalyst rubric's earnings
  assumption (BFLY), the exit (TEAM), the stop-width rule at entry (HTFL), the market-cap floor
  (CHPT), and the top-20 shortlist cut (ABNB).
- **The rubric's record on names it actually judged is 2 of 3** — PLTR and HTFL passed, BFLY wrongly
  downgraded. MRNA and CHPT never reached it.
- **n=7 is thin and it only grows when he names one.** That is the constraint on every conclusion
  drawn from it, and the reason the capture rule above matters more than any analysis of the six.

## Related

- `tests/fixtures/must_not_miss_eps.py` — the machine-readable fixture (30 members; these 6 plus 24
  evidence-sourced, which are return-selected and **not** ground truth for selection quality).
- `docs/methodology/operator_shared_notes.md` — everything else he has shared, verbatim.
- `docs/roadmap/ep_profitability_program.md` — RULE 0 / P1, *"it should not miss a real EP which is
  the true test."*
