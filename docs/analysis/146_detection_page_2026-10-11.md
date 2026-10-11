# #146 — may a breakout register TRIGGERED from TIGHTENING without passing COILED? The DETECTION read (2026-10-11)

**First line: Over 444 trading days, letting a breakout register TRIGGERED from a TIGHTENING-or-better label without
COILED turns 42 TRIGGERED reads into 143. That is +101 reads on 82 flags and 72 names the shipped rule never
registered. The added breakouts closed back under the base low within 10 sessions as rarely as the shipped ones (14% of
99 vs 14% of 42). The 'still above the base high at +10 sessions' check (55% vs 57%) separates nothing: breakouts with
no tightening at all hold 53% (n = 351). With base age matched, breakouts from WATCH fail under the base low 21% of the
time (n = 157), which is a lean, not a significant gap. CDNA 07-31 registers under either reading, 08-25 only if a held
label counts, 09-17 never (0.83x volume). He parked it on 07-12 behind the faithful harness; the harness, not he, then
set the reopen condition (0031 structural stops, a returns question this page cannot meet).**

D1 is at the end, in one line. Nothing was changed; the rule stays his.

Detection only. No returns, no R, no entry, no stop: a TRIGGERED label is a STATE on a board, not a setup (CLAUDE.md
§ SETUP vs FAMILY). The flag strategy is disabled; no order, entry, sizing or safeguard path reads a stage. **⚖ THE LINE:
#146 is a detection criterion and the operator's call; this page measures, it does not flip.**

---

## 0. The decision this serves, in his words

- **#146** (filed 2026-05-28): let a breakout register TRIGGERED from TIGHTENING without first reaching COILED — *"needs
  an N≥10 cohort"*. The 60-day scope window held n = 3 (`docs/analysis/htf_scope_2026-10-10.md` §3, G2).
- **His ruling, 2026-07-12 sitting** (`docs/analysis/lane1_sitting_pack_2026-07-13.md`): **"B2 0026-D2: PARKED"** (behind
  the Block-4 T3 faithful harness; *"do not sign, do not build"*). The park reason was **R**: the incumbent gate read
  tail-positive (+0.78R mean) and the harness that would justify the change was 4/21-faithful.
- **The reopen condition came from the harness, not from him.** The sitting minutes (commit `2ea11a40`, 07-12 08:47 PT)
  record only his ruling above. The condition is the faithful-harness doc's own Dispositions section
  (`docs/analysis/146_faithful_harness_verdict_2026-07-12.md`, commit `8f623bb3`, 07-12 10:19 PT, after the sitting),
  quoted: *"0026-D2 stays PARKED — now with the honest current-classifier table attached. Reopen only if 0031's shadow
  shows structural stops convert this cohort's tail (a named hypothesis)."* No record shows him ratifying it.
- That condition is about stop geometry. This page measures DETECTION (does the breakout hold the level it broke), so
  it **cannot meet the reopen condition**; it answers the question the 05-28 filing asked and the 10-10 scope could not
  (n = 3 → n = 101).

---

## 1. Method and population

| | |
|---|---|
| **Code** | the SHIPPED `flag_detector.compute_flag_metrics` as of commit `b8c941e3` (today's code, including the #697 item 5 one-night hold). Nothing patched, nothing changed. |
| **Window** | scan dates **2025-01-02 → 2026-10-09, 444 sessions** (7.4× the scope doc's 60); warm-up from 2024-11-01 so chains are established. Sub-windows reported: **2026-only (194 sessions)** where board membership can be tagged, and the scope doc's **07-17 → 10-09 (60)**. |
| **Population** | **2,397 tickers**: a SQL superset of the live board (some day with a rolling 40-session high/low ≥ 1.9, close ≥ $4, 20-session mean volume ≥ 350k at some point, common stock / ADR) plus the corpus tickers — `q1_candidates.sql`. The $4 close floor is the universe's $5 gate loosened, a universe-style filter and not one of the detector's own gates, so the 2025 half leaves out sub-$4 names the code would score. Every ticker scored on every trading day with ≥ 60 rows of history (the live scan's floor); the code does every rejection itself. **Leak check: 0 of the 649 stored WATCH-or-better rows since 06-29 belong to a ticker the pre-filter lost** (`leak_check.out`). Raw bars: `mi_daily_closes`, 2023-12-01 →, 1,408,108 rows (`q2_bars.sql`, captured once). |
| **Why raw bars, not stored stages** | stored stages before the 06-27 HTF rebuild came from a retired rule and after it from a hold that re-armed nightly (fixed 10-11); only a replay of today's code over bars measures today's rule. The live RS universe is **tagged afterwards** (2026 only — `mi_stock_scores` starts 2025-12-26), never re-imposed: the 2025 half measures the RULE on the geometry population with board membership unverifiable. |
| **State threading** | per arm from its OWN prior outputs, mirroring the live queries: yesterday's stage + whether that row was a hold (within 5 calendar days), `recent_stages` (within 5 calendar days), prior pivot (within 40 calendar days), 262-row history. Unlike prod every scored day has a row (no universe gaps) — a continuous chain. |
| **Validity (two-sided)** | arm A's raw read reproduces prod's stored raw read on **319 of 319** ticker-days both have since 09-08 (the #592 anchor fix live), and reproduces **all 5** real stored TRIGGERED reads since 06-29 (XMTR 06-30, CHYM 08-19, WDAY 08-28, XHLD 09-09, IOVA 09-14). The other direction: the replay reads WATCH-or-better on **20 ticker-days (9 names) that have no stored row** in that span — checked against the full table (`q6_no_row_check.sql`): **0 of the 20 were scanned by prod at all** (not scanned-and-rejected), so they are universe gaps, not disagreements. Stored STAGES differ on 5 of 319 — prod's re-arming hold vs the one-night hold, by design. |
| **Forward read** | the 10 closes after a raw TRIGGERED read (held labels excluded): held = the +10 close ≥ the base's intraday high (`base_high`, as the task asked), also against the base's highest CLOSE (`base_high_close`, the level the trigger actually tests); "never under" = no close under the level in the 10; "under base low" = any close under `base_low`. Reads with fewer than 10 forward sessions are censored and counted apart. **Split check (A 42 reads, B 143, C 140):** no A, B or C read has a split-like one-day move (> +60% or < −40%) inside its 10-session forward window, except QURE 2025-10-27 → 11-03 (−49%, a real news crash); the from-WATCH set is covered in §9. |

**The four arms differ in exactly one conjunct.** `recent_stages` is read at ONE place in `compute_flag_metrics` — the
`was_coiled_recent` term of the TRIGGERED test (~L1292–1301). Each arm appends `"COILED"` to the arm's real
`recent_stages` when its licence holds, and nowhere else is touched:

| Arm | TRIGGERED licence (the breakout leg — close over the base's highest close on ≥ 1.5× the base's recent volume — is identical in all four) |
|---|---|
| **A shipped** | COILED today, or a STORED COILED label in the 5-calendar-day window (the live rule). 2 of the 42 shipped reads go by the same-day path (LEU 2025-05-23, XMTR 2026-06-30). |
| **B D2, stored** | A's licence **or** any STORED label in the 5-day window is TIGHTENING / COILED / TRIGGERED — **held labels count** (the window half of the COILED licence with the label widened; how 0026-D2 would be coded). B and C add only the window half: a breakout whose OWN day reads TIGHTENING is not licensed by them (§9). "TIGHTENING-or-better" includes TRIGGERED, so a re-trigger off an earlier TRIGGERED label counts (§2). |
| **C D2, raw** | A's licence **or** any RAW read in the window (the hold's underlying read) is TIGHTENING / COILED / TRIGGERED — held labels do **not** count. |
| **D no licence** | every qualifying breakout, from WATCH too (the 07-12 harness's "conjunct neutralised") — context for what the TIGHTENING licence itself is worth. |

Probe: `scripts/probes/_146_page/` — `replay_146.py` (the four chains) → `report_146.py` → `report_146.out` (every
number below), `triggered_reads.tsv` (every read with its forward closes). $0; prod read-only, each SQL captured once.

---

## 2. What "from TIGHTENING" means — three readings, and where they differ

The scope doc (G4) asked whether "from TIGHTENING" is the stored label or the raw read, because both CDNA breakouts
fell on a held TIGHTENING label. Measured, the difference is small and lands on three names:

| Reading of "from TIGHTENING" | Extra TRIGGERED reads beyond the shipped 42 (n of 444 sessions) | Of which licensed ONLY by this reading |
|---|---|---|
| yesterday's STORED label is TIGHTENING-or-better (the reading `htf.md`'s item-5 hand-off used) | **88** (derived from arm B's reads, not separately threaded) | — |
| any STORED label in the 5-calendar-day window (arm B) | **101** | +13 over yesterday-only: 9 had a real TIGHTENING 2–4 sessions back followed by INVALIDATED/WATCH days; 1 (GOGO 2025-07-02) was licensed by a real TRIGGERED (the shipped 06-27 read); **3 were licensed by a HELD label over raw WATCH reads** — AVAV 2025-07-17, FLEX 2026-05-29, **CDNA 2026-08-25** |
| any RAW read in the window (arm C) | **98** | 0 that B lacks; B − C = the 3 held-label cases |

**TIGHTENING-or-better includes TRIGGERED labels.** 5 of the 101 extras have no TIGHTENING or COILED label in their
window and were licensed only by an earlier TRIGGERED label: BE 2025-01-23, PL 2025-07-01, GOGO 2025-07-02 (licensed by
the SHIPPED 06-27 read), AVAV 2025-07-17 and URGN 2025-07-22. The shipped rule's COILED licence does not count a
TRIGGERED label. Dropping the 5 leaves 94 settled extras (§4: 52 of 94 held, 13 of 94 under the base low).

**A correction to the scope doc's framing.** What licenses a TRIGGERED read is the window BEFORE the breakout day,
not the breakout day's own label. On **07-31** the prior window holds a **real** TIGHTENING (07-30, range 0.82 / vol
0.60 — prod stored it un-held too), so CDNA 07-31 registers under every reading; the "held TIGHTENING over raw
WATCH" the scope doc cites is the 07-31 row's OWN label, written after the fact. On **08-25** the prior window is
08-20 (held TIGHTENING, first-night hold under today's code), 08-21 and 08-24 (raw WATCH): the stored reading
licenses it **by the one held night, which sits exactly on the window's edge (08-25 − 5 days = 08-20)**; the raw
reading does not. The hand-off's "CDNA 08-24 is a raw WATCH, so 08-25 is not from TIGHTENING at all" is the
yesterday-only reading; it is correct for that reading and not for arm B's.

---

## 3. Both directions — what each licence admits

| Arm | Raw TRIGGERED reads (n, 444 sessions) | Distinct flags (ticker + pivot) | Names | 2026-only reads (194 sessions) | Scope window 07-17 → 10-09 (60 sessions) |
|---|---|---|---|---|---|
| **A shipped** | **42** | 36 | 34 | 14 | 4 (CHYM 08-19, WDAY 08-28, XHLD 09-09, IOVA 09-14) |
| **B D2 stored** | **143** | 118 | 106 | 52 | 14 |
| **C D2 raw** | **140** | 116 | 105 | 50 | 13 |
| **D no licence** | **498** | 428 | 288 | 184 | 39 |

- **Extras B − A: 101 reads on 82 flags and 72 names the shipped rule never registered** (the table: 118 − 36 flags,
  106 − 34 names). C − A: 98 reads on 80 flags and 71 names (116 − 36, 105 − 34). Counting flags and names among the
  extra reads themselves gives 85 and 81 for B (83 and 80 for C), because 3 flags (CDTX, GOGO, XMTR) and 9 names (ATAI,
  CDTX, CMP, GOGO, NRGV, PL, RLMD, URGN, XMTR) are ones the shipped rule already registered. Nesting verified both ways
  (0 reads absent in each direction): every shipped read is in B and in D, every B read is in D, every C read is in B —
  A ⊂ B ⊂ D and C ⊂ B.
- **Breakouts from WATCH** (in D, licensed by neither B nor C): **355 reads** — 3.5× what the TIGHTENING licence admits.
- **The 101 extra reads, by name** (a flag that read twice is listed on each read; the 101 reads carry 85 flags and 81
  names, of which 82 and 72 are new to the shipped rule):
  - **2025 (63 reads):** SUPV 01-02, OPFI 01-03, CRNT 01-06, GEO 01-08, BE 01-21, BE 01-23, HSAI 01-30, HSAI 02-06,
    AEVA 05-05, AEVA 05-06, MVST 05-12, ODD 05-22, CMP 05-27, CRMD 06-05, MTSR 06-09, MTSR 06-10, CVAC 06-12, CRDO 06-18,
    PL 06-26, PL 06-27, PL 07-01, GOGO 07-02, EYPT 07-09, PCT 07-09, CAR 07-10, AVAV 07-11, OUST 07-15, AVAV 07-17, ATAI 07-18,
    CDTX 07-18, AEHR 07-21, IREN 07-21, PL 07-21, URGN 07-21, PAYS 07-22, URGN 07-22, PAYS 07-24, NNE 07-25, PSIX 07-31,
    JOBY 08-04, PSIX 08-08, ZEPP 08-29, ZEPP 09-02, URGN 09-08, UUUU 09-09, WULF 09-09, WULF 09-10, TLS 09-11, RKLB 09-12,
    UUUU 09-15, FBIO 09-22, DNTH 09-29, IHRT 10-06, MLYS 10-10, OKLO 10-10, NRGV 10-13, AMLX 10-15, QURE 10-27, RCUS 11-20,
    CGEM 12-08, SGML 12-09, PACS 12-12, ALTO 12-18.
  - **2026 (38 reads):** AXGN 01-09, TYGO 02-04, AAOI 02-20, AXTI 02-20, AUGO 02-23, FTAI 02-24, FTAI 02-26, RLMD 03-31,
    BW 04-06, ICHR 04-08, AOSL 05-06, VICR 05-11, TSEM 05-13, NRXP 05-15, CLOV 05-28, NBIS 05-28, FLEX 05-29, COHR 06-02,
    VECO 06-04, VECO 06-09, AIP 06-12, REPL 06-17, AVR 06-18, CEVA 06-18, EVC 06-23, CLOV 06-26, XMTR 06-26, DDOG 07-09,
    SLN 07-22, CDNA 07-31, HELP 08-04, STTK 08-04, CDNA 08-25, SMWB 08-26, SMWB 08-27, CHPT 09-18, EFOR 10-01, HTFL 10-05.
  - Each read's volume, base age, forward verdict and licence window: `scripts/probes/_146_page/report_146.out` §F.
- Board shape (arm A, median per session over this population): WATCH 8 · TIGHTENING 2 · COILED 0 · TRIGGERED 0 — the
  live RS board reads 5 · 1 · 0 (scope doc §3); this population is wider, by design.
- The scope doc named **3** COILED-only breakouts in its 60 days (CDNA 07-31, CDNA 08-25, EFOR 10-01): **all 3 appear
  as B extras here**, with 7 more in the same 60 days — SLN 07-22, HELP 08-04, STTK 08-04, SMWB 08-26 and 08-27, CHPT
  09-18, HTFL 10-05. Checked against prod's stored rows (`q3`): **6 of the 10 were on the live board that day** (CDNA ×2,
  HELP, CHPT, EFOR, HTFL — each stored TIGHTENING or held-TIGHTENING on the read date) and **4 were not** (SLN, STTK, SMWB
  ×2: no stored row, the RS universe never scanned them). **On the board is not the same as registered live:** HELP
  08-04 had no stored TIGHTENING-or-better row in prod's prior 5 calendar days (its first stored row is the 08-04 scan),
  so live D2 would have registered 5 of the 10 (CDNA ×2, CHPT, EFOR, HTFL). The scope doc's "3 of 15" came from a different frame (TIGHTENING
  runs with a close over the FIRST day's base high); CHPT 09-18 sat in its G3 reset list, and HELP 08-04 is licensed here by
  a 08-03 TIGHTENING read the live board did not store (no row that day — the continuous-chain caveat, §9). HTFL 10-05 is
  censored (4 forward sessions). GSHD and QMCO register in no arm — their qualifying close came after the pivot re-anchored
  (`base_age_0`), before any breakout test runs.

---

## 4. Detection quality — did the breakout hold the level it broke?

Full window, raw reads with 10 forward sessions (censored counted apart):

| Set | n settled (censored) | +10 close ≥ base_high (held) | fell back under base_high | never closed under base_high in 10 | closed under base_LOW within 10 | +10 close ≥ base_high_CLOSE (the trigger level) |
|---|---|---|---|---|---|---|
| **A shipped reads** | **42** (0) | **24 (57%)** | 18 | 12 (29%) | **6 (14%)** | 26 (62%) |
| **B extras** (D2 stored) | **99** (2) | **54 (55%)** | 45 | 33 (33%) | **14 (14%)** | 59 (60%) |
| **C extras** (D2 raw) | **96** (2) | 52 (54%) | 44 | 32 (33%) | 14 (15%) | 57 (59%) |
| B extras licensed ONLY by a held label | **3** (0) | 2 | 1 | 1 | 0 | 2 |
| **D extras from WATCH** (neither licence) | **351** (4) | 186 (53%) | 165 | 99 (28%) | **85 (24%)** | 220 (63%) |
| D all qualifying breakouts | 492 (6) | 264 (54%) | 228 | 144 (29%) | 105 (21%) | 305 (62%) |

2026 only (board membership taggable), same columns:

| Set | n settled (censored) | held at +10 | fell back | never under in 10 | under base_LOW within 10 |
|---|---|---|---|---|---|
| A shipped reads | **14** (0) | 8 (57%) | 6 | 3 (21%) | 4 (29%) |
| B extras | **36** (2) | 22 (61%) | 14 | 11 (31%) | 3 (8%) |
| C extras | **34** (2) | 20 (59%) | 14 | 10 (29%) | 3 (9%) |
| D extras from WATCH | **129** (3) | 70 (54%) | 59 | 32 (25%) | 25 (19%) |
| **B extras the live board would plausibly have held** (RS leader — rank ≤ 200 or `rs_1m` ≥ 80 — on some day in the prior 25 sessions, AND close ≥ $5 AND 20-day $-volume ≥ $5M) | **30** (2) | 20 (67%) | 10 | 11 (37%) | 3 (10%) |

**Reading.** **The "held at +10" column cannot tell any group apart.** It reads 57% for the shipped reads (n = 42), 55%
for the D2 extras (n = 99), 53% for breakouts from WATCH with no tightening label behind them (n = 351) and 54% for every
qualifying breakout (n = 492). A measure that sees no difference between any groups cannot show that COILED does
nothing, so "55% vs 57%" is not a finding. **Only one column differs at all: closed under the base low within 10
sessions.** There the D2 extras read 14% of 99 and the shipped reads 14% of 42: **no difference detected at this sample
size.** Breakouts from WATCH read 24% of 351, but **base age is unmatched there** (median 6 vs 12; a younger base has a
higher base low, so the column is easier to hit). With base age matched at 7 sessions or more, WATCH is 33 of 157 (21%)
against 14 of 99 (14%, D2 extras) and 6 of 38 (16%, shipped) — **a lean, not a significant gap.** In 2026 alone the same
column reads 4 of 14 (shipped) vs 3 of 36 (extras): too few to read either way. The shipped-vs-extras comparison is clean
on base age (median 12 vs 12). The COILED prerequisite blocks about 70% of the TIGHTENING-licensed breakouts (101 of
143), and on this page's measures no difference was detected between those it blocks and those it passes. The 5 extras
licensed only by an earlier TRIGGERED label (§2) do not move this: without them 52 of 94 held (55%) and 13 of 94 closed
under the base low (14%). The 2026 board-plausible subset (n = 30) holds 67% vs 57% for the shipped reads — context
only, since the held column separates nothing.

Board membership of the 2026 reads (n = 38 B extras, 14 shipped): in the live organic universe on the read day 25 of 38
vs 11 of 14; an RS leader on some day in the prior 25 sessions 32 of 38 vs 13 of 14; price/$-volume gates 35 of 38 vs
14 of 14. That tag is soft: against prod's stored rows it gets 3 of the 11 extras since 06-29 wrong (SLN and STTK tagged
as RS leaders but never scanned; CHPT on the board but not tagged), so "roughly 5 of 6 extras were names the board was
scanning or carrying" is an approximation, not a count to lean on. **Exact, where prod's stored rows exist (since
06-29): 7 of the 11 B extras were on the live board that day** (DDOG 07-09, CDNA 07-31 and 08-25, HELP 08-04, CHPT
09-18, EFOR 10-01, HTFL 10-05 — each stored TIGHTENING or held-TIGHTENING on the read date) and 4 were not (SLN 07-22,
STTK 08-04, SMWB 08-26 and 08-27 — never scanned); all 5 shipped reads in that span were on the board. **On the board is
not the same as registered live:** HELP 08-04 had no stored TIGHTENING-or-better row in prod's prior 5 calendar days, so
live D2 would have registered 6 of the 11 (DDOG, CDNA ×2, CHPT, EFOR, HTFL).

Volume behind the reads (context; the 1.5× leg is identical in every arm): median breakout volume 2.05× (A), 1.98×
(B extras), 1.88× (from WATCH); median run-up 144% / 130% / 120%; median base age 12 / 12 / 6 sessions.

---

## 5. CDNA — the three breakouts the task names

| Date | Arm A (shipped) | Arm B (stored) | Arm C (raw) | What licensed or blocked it |
|---|---|---|---|---|
| **07-31** | TIGHTENING (held over a raw WATCH) — breakout close 43.71 > 39.73 on **3.08×** volume, no COILED | **TRIGGERED** | **TRIGGERED** | 07-30 was a REAL TIGHTENING (range 0.82, vol 0.60) in both prod and the replay → either reading licenses it. Held: the +10 close stayed above the base high, never closed under it. |
| **08-25** | WATCH — close 50.80 > 48.61 on **1.61×**, no COILED | **TRIGGERED** | WATCH | Prior window 08-20 held TIGHTENING (raw WATCH), 08-21 and 08-24 raw WATCH. Only the stored reading licenses it, by the one held night on the window's edge. Held: +10 close above the base high, never under. |
| **09-17** | TIGHTENING (range 0.68, vol 0.90) | TIGHTENING | TIGHTENING | **No arm registers it, D included: the close over the base's highest close came on 0.83× volume, under the 1.5× leg.** The volume leg, not the COILED prerequisite, is what blocked September. |

The replay's CDNA chain equals prod's stored chain on every raw read from 07-27 to 09-18 (`report_146.out` §G); the
only differences are the held labels prod kept on 08-21 → 08-25 under the old re-arming hold.

---

## 6. His labelled corpus under each arm

Every date is a label he brought in (`tests/fixtures/htf_labelled.py`, `docs/methodology/operator_shared_notes.md`).
n = 10 names, 27 labelled dates.

| Example (his label) | Date(s) | Arm A | Arm B | Arm C | Why — and what D2 changes |
|---|---|---|---|---|---|
| **CDNA** — *"one of the more textbook High Tight Flags"* | 08-18, 08-19 | TIGHTENING | TIGHTENING | TIGHTENING | Hit on both days, every arm. D2 then registers the 08-25 breakout under the stored reading only (§5). |
| **CDNA** — *"HTF… still long"* (09-24) | 09-14 → 09-17 | TIGHTENING | TIGHTENING | TIGHTENING | Hit; the 09-17 break fails the volume leg in every arm (§5). 09-24 reads `base_age_1` in all arms because its pivot is 09-22 (the pivot moved to 09-16 on the 09-18 scan, to 09-18 on 09-21, then to 09-22 on 09-23; scope doc G3; sequence from the independent check, not in `report_146.out`). |
| **HNGE** — *"high tight flag"* | 08-21, 08-24 | `runup_41%_below_90%` | same | same | Rejected before the stage machine (pole window, ruled 09-16). D2 cannot touch it. |
| **MRNA** — *"a touch deep (~26%)"* | 09-11, 09-15 / 09-16 / 09-17 | `flag_low…below_75%` / INVALIDATED (SMA20 by 5¢) / `ma_stack_not_stage2` | same | same | Rejected on depth, then invalidated (ruled 09-18). D2 cannot touch it; no arm registers his 09-17 breakout. |
| **MRNA** — *"model book looking HTF"* | 09-24 | `base_age_0` | same | same | Same post-breakout reset. |
| **GH** — *"flat basing… broke out"* (06-27 review) | 06-24 → 06-26 | `runup_79%`, then `base_age_0` | same | same | Under today's 90% pole GH never reaches the stage machine (June ran under the retired 50/60 rule). |
| **HNGE** — *"clear tight basing, clear break out"* (06-27) | 06-24 → 06-26 | `runup_67%`, then `base_age_0` | same | same | Same. |
| **HPE** — *"a good candidate for HTF or delayed entry"* (pointer) | 06-02 | `base_age_0` | same | same | The gap day itself; not a flag yet. Recorded, not scored. |
| **NCI** — *"not valid"* (negative) | 06-26 | `adv_152k_below_500k` | same | same | Correctly rejected in every arm. |
| **ATAI** — *"a buyout so the HTF is invalid"* (negative) | 07-24 | COILED | COILED | COILED | As recorded in the fixture: the function reads COILED, the M&A layer above it rejects. Unchanged. |
| **OUST / SHAZ / REPL** — *"i don't see HTF in those 3 names at all"* (negatives, 09-04) | 06-29 / 06-29, 06-30 / 08-10, 08-11 | `flag_low…` / `flag_low…` / `base_age_1..2` | same | same | All rejected on his dates in every arm. |

**Extra TRIGGERED reads D2 would have written on corpus names, on dates his labels did not cover:** CDNA 07-31 and 08-25
(above); **REPL 2026-06-17** (1.98×, held at +10 after dipping under the base high); **OUST 2025-07-15** (2.34×, fell back); **ATAI 2025-07-18**
(4.98×, held — a 2025 flag, a year before the buyout). His sign-offs were about specific dates; these are different
flags and have not been judged — listed, not inferred either way. HNGE, MRNA, GH, HPE: no arm changes a single row.

---

## 7. Side table (G8) — his "ATR falling" read against our range / volume ratios

His tightness read (MRNA chart, 09-16: *"ATR(14) 11.4 and FALLING"*, a drawn down-trendline) is a slope across the
flag; ours is the base's last 5 sessions against its first 5 (range on true-range %, volume on shares). Measured on his
labelled dates, n = 8 (5 carry both readings; the three `base_age_0` rows have no base to ratio):

| Example, date | Our stage | ATR-14 at the date ÷ at the pole top | ÷ at the first base day | Our range ratio (≤ 0.75 = tight) | Our volume ratio (≤ 0.70 = drying) | Do the two reads agree? |
|---|---|---|---|---|---|---|
| CDNA 08-19 | TIGHTENING | **0.79×** (falling) | 0.78× | 1.00 (not tight) | 0.69 (drying) | **Stage level: yes** — our stage is TIGHTENING because the volume ratio is 0.69 (≤ 0.70), agreeing with his falling ATR. **Range ratio alone: no** (1.00, no contraction) |
| CDNA 08-25 (breakout day) | WATCH | **0.66×** | 0.65× | 1.29 (loosening) | 0.97 | **No** — ATR down a third, our ratios read looser |
| CDNA 09-17 | TIGHTENING | 1.06× (flat / up) | 1.04× | **0.68 (tight)** | 0.90 | **No, the other way** — our range says tight, his ATR does not |
| HNGE 08-24 | rejected (pole) | 1.04× | 1.03× | 1.41 (rc) | 1.26 (rc) | Yes — both loose |
| MRNA 09-16 | INVALIDATED | 0.85× | **0.68×** | **0.40 (rc)** | **0.18 (rc)** | Yes — both tight (his chart's ATR down-trend; our ratios agree; the code returned INVALIDATED on SMA20 — close 145.62 vs 145.67, by 5 cents — before computing the ratios, so they are recomputed. The depth rejection was 09-11 and 09-15, not 09-16) |
| HNGE 06-25 (June) | rejected (pole) | 0.94× | 0.94× | 1.00 (rc) | 1.00 (rc) | ~ flat both |
| GH 06-25 / HPE 06-02 | `base_age_0` | 1.02× / 1.49× | — | — | — | no base to ratio under today's pivot |

(rc) = recomputed with the code's own formula on a row the code rejected before that step. **Reading: on the 5 dated
examples that carry both, our stage agrees with his ATR read on 3 (CDNA 08-19, HNGE 08-24, MRNA 09-16) and disagrees on
2 (CDNA 08-25 and 09-17, in opposite directions). On the range ratio alone it agrees on 2 and disagrees on 3 — all three
CDNA dates.** His ATR slope and our first-5-vs-last-5 ratio are different measurements of "tightening"; n = 5 says
they are not interchangeable and says nothing about which is right. Carried both ways, not a proposal.

---

## 8. D1 — his decision, one line

**D1 — #146 (letting a breakout register TRIGGERED from TIGHTENING without COILED): over 444 trading days it would have
turned 42 TRIGGERED reads into 143, and the 101 added breakouts fell back under their base low within 10 days as rarely
as today's (14% of 99 vs 14% of 42). The 'held above the base high' check cannot separate anything (even breakouts with
no tightening hold 53%), so the evidence is 'no harm seen', not 'proven as good'. CDNA's 07-31 and 08-25 breakouts
register (08-25 only if a held label counts; 09-17 never, on volume). You parked it on 07-12 behind the faithful
harness; that harness then recommended it stay parked unless structural stops convert the tail, a returns question this
page cannot answer. Recommendation: unpark, with the rule being 'any TIGHTENING-or-better label in the 5 calendar days
before the breakout, held labels counting', through CHANGE_PROCESS with this page as the detection evidence and
expectations written first; no money reads the label, so no shadow step. Your call.**

---

## 9. What this does not answer

- **Returns.** Nothing here is R. His 07-12 park was about R; the reopen condition, set afterwards by the faithful-harness
  doc, is about stop geometry (0031). A +10-session close above a level is a chart fact, not an outcome, and 10
  sessions is one horizon chosen before the pull.
- **The "held at +10" check carries no conclusion.** It reads 53% to 57% in every group, breakouts with no tightening
  label included (53%, n = 351), so it cannot say whether COILED or the TIGHTENING licence matters. The one column that
  moves, closed under the base low within 10 sessions, shows no difference between shipped and extras at these sizes
  (14% of 99 vs 14% of 42); the evidence for unparking is "no harm seen", not "proven as good".
- **Whether the live board would have scanned the 2025 reads.** `mi_stock_scores` starts 2025-12-26; 63 of the 101 B
  extras are 2025 reads measured on the geometry population with board membership unverifiable. The 2026 tag (§4) is
  the honest sub-window, n = 38.
- **The board-membership tag is an approximation.** "RS leader on some day in the prior 25 sessions" stands in for the
  universe carry (#697 item 2, which keeps a name 5 sessions after WATCH-or-better and 25 after TIGHTENING-or-better);
  the exact carry depends on which days the live board wrote a row and cannot be rebuilt from bars. Against prod's
  stored rows it gets 3 of the 11 extras since 06-29 wrong (§4).
- **A continuous chain, not prod's.** Every scored day has a row here; live, a name absent from the universe has no row,
  so a licence window live can be emptier than here. HELP 08-04 is the case in point: on the board that day, but no
  stored TIGHTENING-or-better row in the prior 5 calendar days, so live D2 would have registered 6 of the 11 extras
  since 06-29, not 7 (§4). Validity was checked on raw reads where both exist (319 of 319), not on gap days.
- **The hold rule in the stored history.** Prod's rows before 10-11 carry the re-arming hold; this replay uses the
  documented one-night hold now shipped. The 4 real TRIGGERED reads in the scope window are unchanged either way.
- **The WATCH comparison is base-age-confounded, and only a lean.** Breakouts from WATCH have a median base age of 6
  sessions against 12 for the licensed sets, and a younger base sits closer to its own low; the 24%-vs-14% "closed under
  the base low" gap narrows to 21% (33 of 157) vs 14% (14 of 99) and 16% (6 of 38) with base age matched (≥ 7
  sessions), is not matched on anything else, and is a lean, not a significant gap. The shipped-vs-extras comparison
  (12 vs 12) does not have the base-age problem.
- **The volume leg.** Every arm keeps the 1.5× leg; the scope doc found it blocks twice as many TIGHTENING breakouts as
  the COILED prerequisite (6 of 15 vs 3 of 15). Not measured here — a different question, and CDNA 09-17 is its example.
- **Splits inside the WATCH set's forward windows.** The A, B and C reads are clear (§1). Five from-WATCH reads carry a
  split-like one-day move (ARCT 2025-10-21, FMFC 2025-10-07, GANX 2025-12-05, NVA 2025-10-10, POAS 2026-02-11), not
  judged split or real; dropping them gives 81 of 346 under the base low (was 85 of 351) and 32 of 156 base-age-matched
  (was 33 of 157), so the reading does not change.
- **The breakout day's own tightness is not licensed.** Arms B and C read the 5 days BEFORE the breakout; the shipped
  licence also takes COILED on the breakout day itself (2 of the 42 shipped reads do, LEU 2025-05-23 and XMTR
  2026-06-30), and arm B adds only the window half. The independent check found 24 of the 355 "from WATCH" breakouts
  reading TIGHTENING on the breakout day's own tightness (range ≤ 0.75, volume ≤ 0.70 or a fresh base) and so left out
  of B: 13 of 24 held at +10, 2 of 24 closed under the base low, 6 in 2026, 0 in the scope window. So "no tightening"
  in the WATCH comparison means no tightening label in the 5 days before; those 24 read tight on the day itself. The 24
  are that check's count: `triggered_reads.tsv` carries the range and volume ratios but not the fresh-base path, so
  the file alone does not reproduce them (the range-and-volume test finds 4).
- **The population is a superset of the board, not of the detector.** The $4 close floor is a universe-style filter, so
  the 2025 half leaves out sub-$4 names the code would score (§1).
- **n = 5 on the G8 side table.** The two tightness measurements disagree on all three CDNA dates on the range ratio
  alone and on two of them (08-25, 09-17) at the stage level — a fact about CDNA, not about either measurement.
- **The corpus is n = 10 names.** HNGE, MRNA, GH and HPE are decided by gates upstream of the stage machine; no reading of
  #146 reaches them, and this page does not re-open those rulings (09-16, 09-18).
