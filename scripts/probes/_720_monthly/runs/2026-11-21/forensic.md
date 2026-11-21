# #720 forensic classes, window to 2026-11-21 (39 closed trades, written by inspection from the row fields)

| class | L1 era_c | L1 era_d | L1 era_e | L3 bp1 | total |
|---|---|---|---|---|---|
| variance | 1 | 4 | 2 | 0 | 7 |
| entry-quality | 0 | 0 | 0 | 1 | 1 |
| entry-mechanics | 2 | 1 | 0 | 0 | 3 |
| exit-discipline | 4 | 1 | 4 | 6 | 15 |
| regime | 0 | 2 | 1 | 9 | 12 |
| can't tell | 0 | 0 | 0 | 1 | 1 |
| n | 7 | 8 | 7 | 17 | 39 |

Every cell is n < 10 except L3 (17, of which 5 are in the excluded list). Nothing here is a verdict; the class is one reading of one row.

- **L3 breakout (16 stop-outs + MTW operator close):** 12 of 16 never got past +0.5R; the 12 entered 11-17 or later were all regime Crisis and all stopped within 3 days. 9 are classed regime because their own fields show a clean fill and a stop within 0.15R of -1.0R; the fields cannot separate that from a weak entry rule (n 9, one regime).
- **Stop fills (mechanics, not outcome):** ARDT -1.27R, BRKR -1.44R, AMLX(L3) -1.17R and CRWV(L1) -1.60R filled through the stop; ZYME was an after-hours refusal sale (fixed 11-21, d6796470). Classed exit-discipline, kept apart from the regime losses.
- **L1 (22 trades):** 9 are exit-discipline (profit given back from a +1.0R to +5.1R peak with a stop or trail as the only exit); the post-exit high is above the exit on all 8 measurable, but that is a 10-session maximum and nearly always is, so it does not prove the exit early. VICR and KOD (the two >= +4R) are variance.
- **L1 entry mechanics:** only HOOD (+2.13% over trigger) and PENG (+4.35% over trigger, 2.73 ADR stop) are fill defects; MRVL is a 0.72 ADR stop hit 31 min after fill that then ran +1.15R. L1 regime-classed: 3 (DFTX, HUM, RSKD), all clean fills with stops at day 0-3 in Correcting.
- **Not in the 39:** CYRX 11-17 is not a fill (its only bar at/above 20.37 was 09:44, before the 09:45 submission; max high after submission 20.29), so the earlier would_have_filled label was a labelling bug; EVER 11-20 is an after-hours stop refusal sale, same fix as ZYME.
