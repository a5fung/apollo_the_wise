# READER PROMPT — date the setups Qullamaggie graded in ONE stream (one reader per stream)

> VERSION: v1 scored 66% (39/59 agreed rows within one session; 20/24 good setups) on 2020-08-10 with a Fable reader.
> v1.1 (this file) adds the five fixes marked **[v1.1]** below, found by that calibration; v1.1 is UNTESTED.

You are the single reader for stream `{VIDEO_ID}` (`{TITLE}`), uploaded `{STREAM_DATE}` (the stream day; his "today" and
"Friday" are relative to it). You work ONLY from his captioned words and the daily bars. No network, no subagents, no
git, read nothing outside the files named here, write only under `{OUT_DIR}/`. **NEVER read a bar dated 2025-01-01 or
later** (the bar tool refuses them; do not go around it). Your token budget is the stream's captions once plus about
2-3k tokens of bars per graded name — do not print whole years of bars.

## Inputs

1. `{OUT_DIR}/captions.txt` — the stream's captions, one line per caption cue: `h:mm:ss words`. Read the WHOLE file
   once, start to end. Machine extraction finds only a fraction of the names he grades (on 2020-08-10 it found 18 of ~50),
   so the anchor rows below are a floor, not the list.
2. `{OUT_DIR}/anchors.tsv` — the machine-extracted graded mentions for this stream (`ticker`, `where` = time, `tier`,
   `kw_list`, `status_at_ref`, `bars_symbol`, `quote1`). Every anchor gets a row in your output (kept or dropped with
   a reason). Add a row for every other name he GRADES as a setup that the extractor missed.
3. Bars: `python bar_check.py cands SYMBOL START END` (breakout-candidate sessions with the measures) and
   `python bar_check.py view SYMBOL START END [--raw]` (one line a session). Bars are split-adjusted and keyed by TODAY's
   symbol: if a ticker has no bars, try `bars_symbol` from the anchor row, then `rename_map.tsv`; if still none, write
   the row with `ticker_conf=no_bars`. His price cues are as-traded — use `--raw` to compare them.

## Step 1 — confirm the name and his grade from his words

Captions mis-hear tickers ("cell h" = CELH, "i know" = INO, "pellet on" = PTON, "am i k" = MIK, "nvx" = NVAX). Resolve
the ticker from the sound, the alphabetical order of his scan (he walks scan results A→Z), the chart facts he states
(price level, ADR, sector, "up 300%", earnings date) checked against the bars, and the anchor rows. Give `ticker_conf`
high / medium / low; if two tickers fit and the bars cannot split them, write `ticker_conf=low` and name the alternative in `why`.

His GRADE is the strongest grading phrase he attaches to THAT setup (not to the stock in general):
- tier A: "perfect", "five-star" or more, "really good", "very good", "incredible", "4.5 stars", "such a good one", "memorize this"
- tier B: "good setup", "decent", "pretty decent", "a setup", "3.5-4 star", "nice"
- tier C: "okay", "maybe", "potential", "not that clean", "c-star", "3-star", "secondary", "variation", "not that obvious"
- NOT a setup (verdict `non_setup`, no date): "no setup", "nothing here", "where's the setup", "too choppy / sluggish",
  "broken setup", "not what I'm trying to teach you" / "not really the method" / "alternative setup" (SPG, airlines, cruise
  lines on 2020-08-10), a buyout, an earnings/EP buy ("bought it on earnings"), a short, a chart he dismisses for low ADR
  ("ADR 1.7, never gonna make money") — UNLESS he says the chart itself is a good setup ("it's a good setup, don't get me
  wrong, the only problem is the ADR" → keep, note the ADR remark), a stock with no bars he just names.
  Rows for these are KEPT in the TSV with `verdict=non_setup` so the drop is auditable; they carry no date.
  **[v1.1]** EXCEPTION: a chart he excludes from his METHOD but still trades or grades (SPG: "not what I'm trying to teach you" yet he bought it; an ETF; a low-ADR chart he calls a good setup) gets `verdict=weak_setup`, tier C, AND a date — the exclusion goes in `why`. Only charts he REJECTS carry no date.
  **[v1.1]** "this one too", "and here", "right here (again)" after a graded chart = ANOTHER setup row on the same ticker, never a restatement; if the ticker has no bars, still write the row (`ticker_conf=no_bars`) and name the previous chart's ticker as the alternative.

One stock can carry SEVERAL setups ("a couple of good setups ... one is right here ... and then there's actually a good
setup here"): one row per setup, `setup_idx` 1,2,3 in the order he points at them (his pointing order usually walks
left→right on the chart, i.e. oldest→newest, but not always — the bars decide).

## Step 2 — which time frame is he in? (`frame`)

- `past`: "had a setup here", "was a good setup", "the breakout was on Friday", "where we bought it" → the breakout is
  BEFORE the stream date (up to ~6 months back; he mostly points inside the scan's window, e.g. a six-month gainer scan).
- `now`: "is breaking out", "breaking out today", "opening range highs were ...", "the entry was today" → the stream date
  itself (verify on the bars: the stream-date session must clear the base high).
- `forward`: "setting up", "needs a few more days", "could be a setup later this week / tomorrow", "if it breaks out",
  "I'm watching it" → the breakout, if any, is AFTER the stream date. Date it as the FIRST session after the stream date
  (within 15 sessions) whose HIGH clears the base high he is describing; if no session does, write `verdict=no_breakout`
  with the empty date (a real label, not "undatable"). Never read past stream date + 15 sessions for a forward row.
- A sentence like "there was a setup here, this was a potential setup" with no frame words is `past` on a review stream
  (most streams: he reviews charts of names in a list) — say so in `why`.
- **[v1.1]** "could have been a potential [setup]", "would have been", "maybe set up on Friday", "was a decent setup last week" are PAST rows (dated), even when the same breath goes on to a forward remark ("but it is setting up") — write BOTH rows. Calibration missed BLNK-past 7/29 and TFFP 8/07 this way.

## Step 3 — date the breakout session from the bars (the 08-10 rules)

The breakout session = the session whose HIGH FIRST CLEARS THE BASE HIGH — a range expansion on rising volume out of a
sideways / tightening stretch that his words fit. Procedure per setup:
1. **[v1.1]** `cands` lists two kinds of session: (a) the HIGH clears the highest high of the previous 10+ sessions, and (b) a range expansion (>= 1.3 ADR) after >= 3 tighter sessions, even when it clears no prior high — kind (b) is how a "first bounce of the 50-day, undercuts it, tight range, breakout day" prints (CAR 8/05 was invisible to v1). Run it over the window the frame allows (past: stream date − 130 sessions .. stream date; now: the stream date;
   forward: stream date + 1 .. + 15). Each candidate prints: change, range/ADR, vol/50-day, how many prior sessions' highs
   it clears, close position, gap, mechanical base start + length, prior move, k=1.0 low-run on the 10/20/50-day,
   tightening (last 5 vs prev 5), higher lows, the previous day's range/ADR, as-traded close.
2. Match HIS CUES: the prior big move (a setup needs one — `prior` well above 1.3; "makes a big move" first), the sideways
   base, which average it rode (surf10/20/50 runs; "goes from surfing the 10-day to the 20"), higher lows, the tight
   range / narrow candle before (prev_rng small), the volume on the day, a gap-up / opening-range-highs entry, a weak
   close, the follow-through or lack of it (ONLY his own words: "didn't have much follow through", "stopped you out the
   next day", "+260% since", "a double from entry" — and say in `why` when you used them; never use bars after the
   breakout day on your own), the order of his pointing across several setups on one chart, price cues ("sub 1.85 was
   the entry", "high 44s / low 45s") against `--raw`.
3. `view` ±15 sessions around the best 1-2 candidates when the cands line is not enough (the base shape, the candle
   before, undercut-and-reclaim of an average).
4. **[v1.1]** When two candidates fit and his words do not split them, prefer the one with the TIGHTER session before it and the higher volume, then the earlier (v1 lost PENN-2, PLUG, TTD, FVRR-3 by taking the later / "still in it" candidate; the base-high rule must tolerate a one-tick miss, SRNE 7/30). Pick ONE date with `confidence`: high = his cues pin it uniquely; medium = two fit, one fits better; low = a guess
   between several; `undatable` = you cannot place it (no cue words, ambiguous ticker, the chart he points at is not
   in the bars) — give the reason. List the top candidates you weighed in `candidates` (date:reason; ...).
5. If he names the base's start or a support bounce ("first bounce of the 50-day"), put the base start you read in
   `base_start` (else leave it empty and the mechanical rule applies).

Record `used_after_words=1` when his after-the-day words helped choose the date.

## Output — one TSV row per setup, `{OUT_DIR}/dates.tsv`

Columns (tab-separated, header first):
`stream_id  stream_date  t  spoken  ticker  bars_symbol  ticker_conf  setup_idx  verdict  tier  grade_words  frame
breakout_date  confidence  base_start  candidates  cues  used_after_words  why`

- `verdict`: good_setup (tier A/B), weak_setup (tier C), non_setup, no_breakout (forward rows with no clearing session),
  undatable.
- `t` = the caption time of his first word on that setup; `spoken` = the caption spelling; `cues` = his exact cue
  words for that setup, quoted, short; `why` = one or two sentences, plain words.
- Also write `{OUT_DIR}/rules_heard.txt`: every general rule he states in passing (sell rules, "ADR over 5", "never buy
  within 3 days of earnings"), one line each with the time.

## Step 4 — run the automatic bar check and re-read its flags

`python bar_check.py check {OUT_DIR}/dates.tsv --out {OUT_DIR}/flags.tsv`. For every flagged row, re-read his words
and the bars once: either keep the date (write the flag and your reason into `why`: "flag not_rising_vol: he said
nothing about volume; the session clears a 31-session range on 0.9x") or move it. A flag is a question, not a verdict —
four of his 24 good 08-10 setups broke out on below-average volume. Do not iterate beyond this one pass.

## Return

A 5-line summary: rows written (by verdict and tier), dated rows by confidence, flags raised / kept / moved, anchors
dropped and why, your token use (the counter at start and end).
