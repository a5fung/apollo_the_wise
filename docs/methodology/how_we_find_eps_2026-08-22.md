# How we find EPs — where the holes are, and whether to let more in (2026-08-22)

**The short version: the machine now ranks a real EP near the top of its morning instead of
near the bottom — that was this weekend's work. But the selection process is not complete:
the news grade is still the weakest link, and everything new is fitted to the same 26 known
real EPs. On admitting more names with real-time prices: not today — yes around 4 September,
your own condition, if the re-check passes.**

---

## 1. The funnel — every step, why it exists, what it costs

The scanner runs every 5 minutes, 7:00–10:00 AM ET. Each step below throws names away.
The funnel narrows because each step costs more than the one before: watching prices is
free, reading the news costs money, an alert costs your attention, and an entry takes one
of five money slots.

1. **The whole market — about 9,700 names.** Everything with a price. Free.
2. **Must be a real, tradeable stock.** No funds, warrants, or foreign oddities; closed
   above $5 yesterday; traded at least 50,000 shares yesterday. This silently removes about
   2,000 names a day — including roughly **26 gapping names a day that were thrown away with
   no record at all**. As of today those drops finally write a log line (the rule itself is
   unchanged). Why the rule exists: sub-$5 illiquid names are mostly noise, stale quotes,
   and phantom gaps — and on the average they go on to LOSE 19–26% in the next month.
3. **Must be gapping up at least 9%** (was 10% until this Wednesday). A normal morning
   leaves roughly 12 candidates; a wild morning leaves over 100. Why: the gap is the signal
   that news changed what the stock is worth.
4. **Health checks.** Skip if: we already alerted it in the last 60 days (unless fresh
   earnings and a 15%+ gap) · it already ran 75%+ in the past week (that's chasing) · it is
   trading slower than its own normal pace for this time of day. Each kills only a few
   names, but each has killed a real EP at least once — the pace check is the risky one,
   because real EPs trade QUIET (more on that below).
5. **The shortlist: top 20 get graded, because grading costs money.** Reading a name's news
   (web search + SEC filings + the model) costs a few cents per name, so only 20 names per
   scan get it. **Since today the 20 are picked by merit** — mostly by how many dollars the
   stock trades on a normal day, plus a flat credit for having a gap and a bonus for being
   in a hot theme — **not by gap size.** The 20 is a budget line, not a judgement.
6. **The news grade.** The model reads the actual filings and news and calls the catalyst
   game-changing, strong, or routine. Since today a rule layer corrects the model's known
   habits: the top grade now requires real surprise evidence, and a "routine" that is
   actually a real company event on a busy sector day gets bumped up one notch.
7. **The score.** Points for: normal-day dollar liquidity (up to 15 — the one input that
   measurably marks real EPs) · having a qualifying gap (flat 10 — size no longer pays) ·
   the news grade (25 / 15 / 0) · small float · pre-market volume · hot theme. One
   automatic pass survives: gap of 10%+ with the top news grade alerts no matter what.
   **Score 65 or better → alert to your phone.** Historically 2–3 alerts a day; the new bar
   was chosen to keep that unchanged. Scores 50–65 are now written into the morning
   briefing as near-misses — recorded, not tradeable — so a real EP dying just under the
   bar leaves a trace.
8. **The entry.** An alert inside 9:31–9:44 → buy stop at the opening-range high, at most 5
   positions. An alert at 9:45 or later → no trade, ever.

---

## 2. What changed this weekend, and what it bought

- We finally counted every real EP we know of — 26 names, each a winner worth 10 times its
  risk or more. **We kept zero.** Three ever alerted, two were entered, none held five days.
- The root cause: the score paid for exactly the wrong things. Real EPs gap SMALLER and
  trade QUIETER than the junk they compete with — and we paid points for big gaps and loud
  volume. Our own score ranked a real EP in the bottom third of its own morning.
- What shipped (each signed, each revertible with one switch): the score now ranks on
  dollar liquidity · gap size stopped being paid · two backwards components deleted · three
  of the four automatic score passes deleted (they fired 5-to-1 in favour of ordinary
  gappers) · one alert bar for all market conditions, set so alert volume stays flat · the
  shortlist ranks by merit, not gap · the news-grade correction layer went live.
- What it bought, on the same 26: a real EP now typically out-scores about **three quarters
  of its morning's board instead of one quarter**. Every real EP that clears the 9% gap
  floor can now reach an alert — before, only 6 of 25 could, at any grade. MRNA — your
  reference EP, which only alerted because of a freak 33% price print — now alerts on its
  real numbers. And the top news grade went from near-routine (4 in 10 ordinary alerts got
  it) to rare again (about 2 in 10).

---

## 3. Are we complete? No. The gaps, honestly

- **The news grade is still the wall.** A "routine" grade zeroes the news points, and
  routine + a gap under 12% is an automatic skip before scoring — **and that skip still
  reads the UNCORRECTED grade**, the correction layer doesn't reach it. The typical real EP
  gaps about 10%, so for the typical real EP the grader still holds the key. Worse, we
  can't even check the grader: 19 of the 26 real EPs were never graded at all, and 4 of the
  7 that were left no text behind to re-examine. The live record now captures every graded
  name, so this becomes measurable — slowly, for free.
- **Everything new is fitted to the same 26 names.** The score was rebuilt on the very list
  it is judged by. The first honest test is **mid-October**, when this summer's gap days
  are old enough to know which were real.
- **Half the evidence is one morning.** 13 of the 26 happened on April 8 — one tape, one
  market condition. Treat every number above as provisional.
- **7 of the 26 never reach us at any score** — they gapped 8.1–8.7%, under the 9% floor.
  And the delayed price feed misreads gaps by about 4 points on a routine basis, so which
  side of the floor a borderline name lands on is close to a coin flip today (that is the
  real-time question, section 4).
- **The quiet-base idea is not in the score.** Measured three separate ways, it ranked
  backwards or flat every time. The definition finds your MRNA base exactly — it just does
  not RANK names on this data. Parked in the chart-reading lane, not scored, not forgotten.
- **"How much is already priced in" (your P13) is recorded but not scored.** The raw
  inputs are being saved on every graded name so it can be built the moment the news grade
  is trustworthy enough to build it on. Scoring it today would fit it to a broken grade.
- **Names that become liquid ON the gap morning are invisible until the day after.** About
  6 a day of yesterday's illiquid names do $50M+ of trade on the gap day itself — the
  fattest-tailed group in the whole study, and also the worst-crashing one. The fix is a
  same-day liquidity re-check (#584, filed, needs your sign-off), not a lower floor — a
  lower floor also admits the sludge.
- **The 20-name grading cap is a budget, not a judgement.** It has never been re-priced
  since the merit ranking made slot competition meaningful. A few cents a name means
  30 slots costs pennies more; what it really costs is dilution of attention.
- **The buyout filter once killed a real EP worth ~15 times its risk** (QURE). Flagged,
  unresolved.
- **Selection feeds a book that has never held anything.** No fill of any kind has ever
  survived 20 sessions, and the real-EP runs start a week or more out. That is the stop's
  problem, not selection's — the new wider stop now running is the current attempt — but
  perfect selection changes nothing until something can be held.

---

## 4. Can we admit more with real-time prices?

**No — not today. Yes around 4 September, if the re-check passes.** Both sides of it:

- **What real-time buys.** About 4 names a day pass every rule on real prices but never
  become candidates on our delayed feed. Borderline names sit closer to the 9% floor than
  the feed's typical 4-point error, so today the floor decision on them is effectively
  random. TWST was the clean case: over the floor **4 seconds** into the session on real
  prices; our delayed number crossed at 9:45:11 — eleven seconds after the entry window
  shut. You said you would have wanted that trade.
- **Why it was held before.** When real-time admission was last measured (10 August), the
  extra names LOST money — minus 0.6 of a risk unit on average, 80% dead the same day.
  That was under the old tight stop. You ruled: hold, and re-measure once the new stop has
  run 14 full trading days. **That lands around 4 September.**
- **What is different now.** On 10 August, extra admissions were extra noise, because the
  ranking could not tell a real EP from a gapper. Now they compete on merit: the shortlist
  drops its lowest-merit name to make room, and the names that lose slots are thin
  max-gap names — the replay of every logged day found no real EP loses a slot and six
  gain one. The 20-slot grading budget is unchanged, so more admission does mean more slot
  competition — which is exactly what the merit ranking exists to arbitrate.
- **The conditions to say yes**, in order: (1) the new stop runs its full 14 trading days;
  (2) the scheduled re-check (#559) shows real-time names no longer bleed under it — and
  if the stop never fired in the window, that is a valid answer meaning hold; (3) a week
  of the new score live shows alert volume holding at 2–3 a day.
- **Recommendation, one line:** plan to flip real-time admission after the ~4 September
  re-check passes; flip nothing before it. The switch is yours (THE LINE).

---

## 5. What to watch Monday — first market day with all of this live

- **Alert count: should stay 2–3 a day.** If it doubles or goes silent, a switch comes
  back off — every change has one, and the nightly monitor owns the revert triggers.
- **The top news grade should be rare** — about 1 alert in 5, not half of them.
- **The shortlist:** the most liquid real-catalyst name of the morning should sit at or
  near the top of the graded 20. If a name you'd call real falls outside it, that is the
  monitor's first trigger — say so.
- **Read the near-miss section of the briefing.** If real EPs show up anywhere first, it
  is there, at scores 50–65.
- **The invisible drops now write rows** — the ~26-a-day silent kills should appear in the
  scan log for the first time.
- **MRNA is still the one live real EP** — partial banked, remainder at breakeven. It is
  currently the only name that can make the retention count 1 of 26 instead of 0.
