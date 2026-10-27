# #711 step 6b — R5 (side agreement) miss diagnosis, 2026-10-27

Read-only diagnosis of the 20 R5 misses in `03_check.txt` (46 / 66 = 69.7%, bar 90%). No file edited; no R1 containment read for any
statement; nothing after 2024-12-31. Scratch scripts (not committed): the session's scratchpad `dump2.py`, `cap.py`, `quant.py`
(`quant.out` reproduces the registered join from `entries.tsv` on 66 / 66 rows before testing any alternative).

**Verdict: the windows are mostly right — 1 window error confirmed by his own words (SPXL: a blip fill over a footer-confirmed
absence) and 1 probable (LAKE). R5 as specified goes wrong at the session level: it scores statements the panel cannot place on a
side (exits on the entry day, trims and adds, flips, invisible round trips, talk about another day). No action-blind fix tested
reaches 90%: the best single fix reads 72-75%, and all the defensible ones together reach about 76%.**

## The 20 misses

ET clock = the caption time plus the video's median (frame et_time - stream_ts) offset; about ±2 min. "H" = on the panel.

| # | stmt | date | tkr | action | landed | cause | what he said (caption) | panel timeline | why it missed |
|---|---|---|---|---|---|---|---|---|---|
| 1 | O333thFuU40:1521 | 2020-01-22 | LAKE | sell_part | buy d1 | window_wrong (probable) | "I had five thousand shares, I sold some in like 15 bucks" (09:43) | first seen 01-22 09:21 (pre), H 10:13/10:28; **01-23 absent from both full frames (footer_eq at 10:05) but blip-filled**; H 01-27..01-28 pre; gone 01-28 10:28 | blip fill joins 01-22 to 01-27 into one position, so the only sale window is 01-28. Without the blip, the sale window is [01-22, 01-23] at distance 0, so the statement agrees. 01-27: "I bought it initially on Friday" (a re-buy on 01-24?) but also "I never got stopped out". Ambiguous: the other reading is a trim during the hold (cause other). |
| 2 | qmhLHCHRBnM:848 | 2020-02-03 | APT | buy (an add) | sale d0 | other: add on the exit day | "I bought some APT here 6.90 break ... only got filled 15000 ... I'm long 45 thousand" (09:32) | H since 01-23 (01-29 blip-filled); H 02-03 09:26-09:35; gone 10:26 | an add on the day of the final exit, which is 10:07: "APT I just got stopped out of this thing". An add has no window of its own, and the only window touching 02-03 is the sale. The reader's "buy" should be "add" (same side either way). |
| 3 | eTanNJy7c38:35 | 2020-02-12 | SHOP | buy | sale d0 | same_day_round_trip | "I bought a thousand shares of Shopify at 543 market and now it's at 570" (09:21, pre-open) | first seen 02-12 09:22 pre, H all day to 10:30; gone 02-13 pre | 02-13: "I bought Shopify pre-market that I had to sell end of the day". Bought and sold in the 02-12 session; the pre-market first sighting is dated to the previous session (hi = 02-11, R37 "he doesn't buy premarket"), so 02-12 is distance 0 from the sale window only |
| 4 | lZNUaBx_H98:989 | 2020-03-23 | TVIX | shorted | sale d1 | statement_about_another_day | "what gave me the confidence to short it big time on this day when I made 1.3 million" (chart pointing) | short H 03-06 .. 03-24 10:15; gone 03-24 10:37 | talks about a past day; joined on the stream date, which is one session before the cover |
| 5 | T1oQYHFdW-Q:116 | 2020-04-20 | SPXL | covered | buy d1 | window_wrong (confirmed) | "SPXL I covered late day on Friday ... if I'm going to short I may short SPXL" | shorted 04-17 (H 10:01); **04-20: absent from all 7 full frames, footer count = rows read, blip-filled**; H 04-21 pre .. 04-23 | a real round trip (cover 04-17, new short by 04-21; 04-21: "heavily short ... tqq spxl"). The blip merged two positions. Without it: sale window [04-17, 04-20] and new buy window [04-20], so the statement ties and drops out of the score |
| 6 | Feyk4S1vVRk:4359 | 2020-05-06 | RCL | stopped (short) | buy d0 | same_day_round_trip | "RCL I got stopped out ... $20,000 loss ... wasn't a great short setup" (~10:24) | shorted ~10:00 (49:21 "the one I shorted ... RCL"); first seen 10:25 (the stream's last frame); H 05-07 09:25 pre; gone 09:50 | short and stop in one session. The frame at 10:25 is within the clock error of the stop. Still on the panel the next pre-market, so either a partial stop or a re-short ("keep getting stopped out of my shorts in ... cruise lines" 05-07). Ambiguous; not a window error |
| 7 | 7tIk1NhphuQ:641 | 2020-05-13 | NVAX | stopped (short) | buy d0 | reentry_second_position | "Oh NVAX, I got stopped out ... $48,000 loss" (09:41); pre-market "main watch NVAX on the short side" | not seen 05-11..05-13 (05-13 frames all partial); a new position first seen 05-14 10:28, gone 05-15 | an intraday short round trip on 05-13, never on the panel. It landed on the wide buy window [05-11, 05-14] of the NEXT position (05-14) |
| 8 | -4SriUVLDKo:4799 | 2020-05-20 | NNDM | stopped (short) | buy d0 | same_day_round_trip | "I got stopped out of NNDM, took $11,000 loss ... hopefully goes to five six bucks" (~10:28) | borrowed 150k pre-market; first seen 05-20 10:11; H 05-21 all day | 05-21: "I'm still short NNDM from yesterday ... covering some". A stop on the entry session with the short still open (partial, or a re-short), so no sale window that day |
| 9 | m8KjHohwlzM:479 | 2020-06-11 | ZM | sell_part | buy d1 | other: trim on the entry day | "Zoom I bought some yesterday ... then I sold the third into the close" | buy window [06-09, 06-10] (06-10 frames partial); first seen 06-11 09:19 pre; H to 07-20 | a trim on the entry day (06-10); the position runs 6 weeks, so its only nearby window is the buy |
| 10 | YYFwzNZkRDI:4841 | 2020-08-05 | JMIA | buy | sale d1 | statement_about_another_day | "Jumia I bought it on July 20th, a quick triple" | buy window 07-20; last seen 08-04 09:32; gone 09:46 | he names 07-20; joined on 08-05, one session after the sale (R62: the stream date for every day class) |
| 11 | obo0RcmxNNE:1080 | 2020-09-21 | TSLA | stopped | buy d0 | reentry_second_position | "I bought 10,000 shares of Tesla" (~09:32) then "I got stopped out of Tesla, $66,000 loss" (~09:38) | 09-21 frames are pre-market only, no TSLA; a new position first seen 09-22 pre (09-22: "Tesla, I bought it late day") | a 6-minute round trip the panel never saw. It landed on the late-day re-buy's buy window [09-21] |
| 12 | LMrz-rWQqac:324 | 2020-09-25 | ZM | shorted | sale d0 | statement_about_another_day | "Zoom yesterday I shorted it 5 minutes after I cut the stream ... still short most of my shares" (~09:27) | first seen 09-25 09:26 pre; H to 09:35; gone 09:52 | "yesterday" (09-24 = the buy window), said on the morning he covers. The stream date is distance 0 from the sale window, distance 1 from the buy |
| 13 | VOGuzD4wFN8:1264 | 2020-11-02 | TSLA | shorted | sale d0 | statement_about_another_day | "Tesla opening range lows on Friday ... right here is where I shorted it, 405.50" | first seen 10-30 10:54; H 11-02 to 10:05; gone 11-04 pre (no 11-03 stream) | "Friday" (10-30 = the buy window); 11-02 is the last day seen, so the sale window [11-02, 11-03] contains it |
| 14 | YTRrhSIj064:4771 | 2020-12-18 | TAN | sell_unspec | buy d0 | statement_about_another_day | "worst sell decision ever ... bullish back in like 75 area ... and yet I sold it at 85 or so 86" | earlier position 11-16 .. sold 11-30/12-02; 12-14..12-23 frames all partial; next position first seen 12-24 pre | regret about the 11-30/12-02 sale. It landed on the next position's wide buy window [12-14, 12-23] |
| 15 | l4lpLA7vvbg:5842 | 2020-12-21 | PLTR | stopped (short) | buy d0 | same_day_round_trip | "Palantir is stopping me, I have stopped out of half ... now three quarters of my short" (~10:51) | shorted ~10:00, 200k shares; first seen 10:18; H to 12-28 | partial stops on the entry session. 12-22: "PLTR I only bought half size yesterday": he flipped long the same day, so the panel row never empties |
| 16 | l4lpLA7vvbg:6723 | 2020-12-21 | PLTR | covered | buy d0 | same_day_round_trip | "I had over 5 million and then I covered 5 million" (~11:07) | as above | the same round trip and flip |
| 17 | 146r7DqtOXU:292 | 2021-02-23 | AMC | buy | sale d0 | statement_about_another_day | "AMC broke out late day or midday and looks like it's gapping up a little bit, I bought some" (09:20, pre) | 02-22: "nice range break, I hesitated"; first seen 02-23 09:19 pre; gone 09:49 | most likely bought 02-22 (or pre-market 02-23) and sold in the first 20 minutes of 02-23 (02-24: "AMC ... shook me out yesterday ... I just sold it"). Next-morning talk, the plan's 10% allowance |
| 18 | 7jPFXy_nrBE:1164 | 2021-03-19 | UPST | sell_part | buy d1 | other: trim during the hold | "I sold about 20 percent of my UPST ... it went up 40% after my entry" | first seen 03-18 09:38; H to 04-19 | a trim the day after entry; the position runs a month |
| 19 | uX2B8fAMuLE:737 | 2022-02-28 | NUGT | stopped | buy d1 | reentry_second_position | "I'm so pissed I got stopped out of it, I had it like 52 bucks or 53" | no streams 02-23..02-25; absent 02-22 and 02-28; a new position first seen 03-01 09:59 | a position never on the panel. It landed on the next day's re-entry buy window |
| 20 | uX2B8fAMuLE:752 | 2022-02-28 | NUGT | stopped | buy d1 | reentry_second_position | "I got stopped out almost at the low" | as above | **the same utterance as #19, read twice** (6 s apart): a duplicate in the population |

Counts by cause: statement_about_another_day 6 (4, 10, 12, 13, 14, 17) · same_day_round_trip 5 (3, 6, 8, 15, 16) ·
reentry_second_position 4 (7, 11, 19, 20) · other = a trim or add with no window of its own 3 (2, 9, 18) · window_wrong 2
(5 confirmed, 1 probable) · short_side_convention **0** · reader_label_error 0 that change a side (1 duplicate, 1 add read as buy).

**Shorts:** R72 matches the plan: a short's appearance is its entry, so shorted maps to the buy window, and covered/stopped map to
the sale window. None of the 20 misses comes from that convention. Statements where he says "short" miss more often (6 of 10)
because his short holds are intraday (RCL, NVAX, NNDM, PLTR) or talked about the next morning (ZM, TSLA, TVIX). The convention is
not the cause.

## Fix candidates — each measured on all 66, not only the 20 (`quant.out`)

| fix | kind | misses resolved (of 20) | effect on all 66 | fitting risk |
|---|---|---|---|---|
| Blip fill not applied when a full frame's footer count equals the rows read (SPXL 04-20, LAKE 01-23) | real_window_error | 2 (SPXL drops out as a tie, LAKE agrees) | 118 of the 125 blips in the window set are over a footer-consistent absence; 5 of the 66 statements sit on a position containing a blip (4 misses, 1 agree). The audit sample here is 3: SPXL confirmed, APT 01-29 and LAKE 01-23 ambiguous | low motive risk (his words prove SPXL), but broad scope: a step-5 window-build input, so the main loop's disclosed-event call; audit the blips against captions before changing the rule |
| Join `stated_earlier` statements at the stream date minus one session ("yesterday" / "Friday") | join_rule_change | 2 (ZM 09-25, TSLA 11-02 agree) | 47 / 65 = 72.3%: 2 misses agree, 1 agreeing statement (NIO) becomes a tie, 14 unchanged | moderate: R62 refused to infer a day from the words; the plan's text says "the stated day". JMIA (a named date) needs a dated reading, not a shift |
| Clock-level join: a statement said while the landed position is visibly on the panel (first sighting <= its ET clock <= last sighting) is set beside, not scored; otherwise its side is taken by clock | join_rule_change | 11 by exclusion (SHOP also agrees, but at a 0 min margin, so it is not counted) | 27 / 36 = 75.0%: also excludes 19 of the 46 agreeing statements and turns 1 into a miss (HTZ, at 0 min margin). Several calls sit within the ±2 min clock error (SHOP, AMC, RCL, ZM x2, HTZ) | high leverage: a different population, not a lift. Unlike the fork's held-position join (`count_heldjoin.out`, for R1, which sides a mid-hold statement by its ACTION and would make R5 circular), this one ignores the action and excludes. A registered amendment, decided before any re-run |
| Score only stream_day + implied_recent statements | join_rule_change | 7 by exclusion | 29 / 42 = 69.0%: no lift | diagnostic only: shows that talk about other days is not what sinks R5 |
| Pre-market first sighting: the buy window reaches that morning (SHOP: "I bought Shopify pre-market") | join_rule_change (a convention he ruled on, R37, not a window error) | 3 become ties (SHOP, ZM 09-25, AMC) | 42 / 59 = 71.2%: also turns 4 agreeing statements into ties | contradicts his R37 note ("he doesn't buy premarket"): his ruling. Exclusion only, no agreement gained |
| Score `sell_part` / `add` as no side (a trim or add never empties the panel row) | definitional_bug_in_R5 | 2 (ZM 06-11, UPST); APT only if relabelled add | 42 / 59 = 71.2% (4 agreeing trims/adds removed too) | moderate: excludes by action type. A structural reason exists, but the plan's R5 text lists "added" on the buy window |
| Dedupe one utterance read twice (NUGT 737/752) | reader_relabel | 1 | 46 / 65 = 70.8% | low, if applied to every duplicate |
| Invisible round trips that land on a neighbouring position (TSLA 09-21, NVAX 05-13, NUGT), exits on the entry session that leave the row open (RCL, NNDM, PLTR x2), next-morning talk (AMC, TVIX, TAN, JMIA) | not_fixable | 0 | — | the panel's blind spots (the plan's 10% allowance, plus the invisible-trade count) |

All the low/moderate-risk fixes together (blip on the 2 confirmed/probable cases, stated_earlier shift, dedupe): roughly 48 / 63 =
**76%**. That is not computed for the whole set: undoing the blips also changes 3 other positions under the 66 (TVIX, APT, NKLA;
NKLA currently agrees). Still under 90%; about 15 misses remain, all panel blind spots.

## Readout

- The plan's prediction ("the misses mostly stream_day statements on an adjacent window") did not happen: stream_day is 6 / 6 agree.
  The misses are intraday round trips and partials (9), talk about another day (6), invisible trades on a neighbouring position (4)
  and one blip-merged position.
- "A merged position or a late sale window": the one confirmed merge is SPXL (the blip fill). No sale window was found to be late;
  APT 02-03 disappears within the session of its stop.
- Decision for the main loop / him (R5 under 90% under the plan's consequence table): (a) audit the 118 footer-consistent blips, a
  window-build input; (b) whether R5 should be re-specified at clock level as a registered amendment (a different population, about
  36 statements); (c) the pre-market reading, which is his R37 ruling.
