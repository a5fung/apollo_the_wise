# HTF — one decision, for Sunday 2026-09-13

**You are choosing what to DO. The evidence is already gathered; nothing here needs building first.**

## Method and population

**Rows:** `mi_htf_breakout_shadow` breakouts with a SETTLED outcome — **n = 148** — replayed from
stored minute bars under the rules as written today, not from historical trade rows. Full method and
the per-row table: `docs/analysis/610_htf_replay_2026-09-10.md`.

**Entry** = `base_high` on the break day. **Management** = the shipped fixed +3R / −1R bracket.
**Capture** = the share of breakouts that reached +3R before −1R; **25%** is the breakeven for that
bracket, since 3:1 payoff needs one winner in four.

## What was measured

**148 settled breakouts. Capture 16.9% (25 of 148) against the 25% breakeven.** On that population,
under that entry and that exit, the bet loses.

## What that number is, and is not

⚠ Your own correction, 2026-09-10: *"htf as written today may have no edge, not that htf as a setup
have no edge."* The replay tested **our encoding plus one exit bet**:

| tested | NOT tested |
|---|---|
| our candidate definition | the HTF pattern itself — a sourced, externally established setup |
| entry at `base_high` on the break day | anticipation inside the base, or a post-break pullback |
| the shipped fixed +3R / −1R bracket | the #396 management protocol |
| | whether our detector admits the right names — `htf.md` calls the ADR floor a starting value and the flagpole ratio one interpretation of several |

## Two defects in the instrument that produced the number

1. **Impossible fills.** The recorder credits fills at prices that could not have been had.
2. **Split drift.** The shadow stores raw prices; `mi_daily_closes` is retro-adjusted. Any join
   across a split is nonsense — **already 1 of 16 rows** (CDLX traded 185–194 that week; `mi_splits`
   confirms a 1:4 on 2026-07-02).

## The fork

| | what it means | what it costs |
|---|---|---|
| **A — record #397 NO-GO** | HTF breakout entry does not graduate on this evidence | closes a four-month thread; risks killing it on a defective measurement |
| **B — fix the recorder first, then re-measure** | repair the fill assumption and the split join, re-run the same replay | a day or two; the answer changes or it does not, and either way it is trustworthy |
| **C — re-test with the #396 exit** | the same names, managed differently | **the +0.74R mean is 85% five trades — without them it is +0.12R, median −0.16R.** Not yet a real alternative |

## My recommendation: B

**A NO-GO recorded on a defective instrument is the same mistake as a GO.** Both defects are known,
both are in the measuring path, and neither is expensive to fix. C is not ready — its headline
number is five trades wearing a mean.

⚖ This is your call, not mine, and nothing has been flipped or changed while it waits.

## What this does not answer

- **Whether the HTF pattern has an edge.** It tested our encoding plus one exit bet, on names our
  detector admitted. If the definition is wrong, the number describes our filter.
- **Whether a different entry works** — anticipation inside the base, or a post-break pullback.
  Neither was replayed.
- **Whether the 16.9% is even measured correctly.** Two defects sit in the measuring path (above),
  and that is the whole reason option B exists.
- **Anything about the detector's admission bar.** The ADR and ADV floors that cut breakouts 91%
  (#610's own finding) are upstream of this population — these 148 are what survived them.
