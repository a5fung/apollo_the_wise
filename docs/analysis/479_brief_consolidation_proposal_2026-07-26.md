# #479 — Consolidated evening-brief redesign (PROPOSAL, no code changed)

Operator correction (2026-07-20, verbatim intent): the 7/17 #479 pass simplified by
**culling** sections, which orphaned real signal (RISING/ROTATION — restored 7/20 as
#492). The ask is still simplification, but via **consolidation** (fewer, denser,
higher-signal sections), never deletion. **Every signal reachable — inline or via a
verified drill-down.** This document is that redesign, for operator sign-off. No code
was written or deployed; this is a proposal only.

Grounded against `agents/market_intelligence/briefing.py` (current `send_evening_briefing`
/ `_format_evening_briefing`), `channels/telegram.py::_register_commands` +
`_handle_hud_drill_down`, `agents/market_intelligence/agent.py`'s command dispatch +
routing cascade, and prod (`ssh apollo@87.99.134.162`, SELECT-only) for real recent
brief sizes and a real data snapshot (2026-07-24).

---

## 0. The headline finding: signal isn't just orphaned to a command — some of it is fetched and thrown away

Before the inventory: `_format_evening_briefing` in the current code accepts
**eleven** parameters it never uses in its body — carrying **eight** distinct
signals (the wick group is 4 separate params for one signal). `send_evening_briefing`
runs the DB query for each of them, every night, and passes the result in — and the
render function just drops it on the floor. Confirmed by grep (each name appears only
in the signature + the `send_evening_briefing` call site, never inside the function
body):

- `signal_quality_summary` — Friday-only RS-alpha-vs-SPY + EP-hit-rate check
  (`get_weekly_signal_summary`). **Grep confirms this is the ONLY call site in the
  whole repo** — this metric currently has no home anywhere, brief or command.
- `pullbacks` (MA-pullback screener — this one is a *required* positional param, not
  optional-and-unused like the rest, which is likely why it survived unnoticed),
  `sugar_babies` (today's EOD-confirmed 9M prints), `cohort_babies` (persistent
  Pradeep cohort), `ninem_anticipations`, `ep_outcomes` (today's HIGH EP terminal
  states), `wick_today_count/tickers/fill_rate_30d/settled_30d` (one signal, four
  params), `undercut_rallies` — all fetched, all unrendered.

Two formatter functions for this content still exist in the file, fully written,
simply uncalled: `_format_ep_outcomes_section` (line 913) and
`_format_signal_quality_section` (line 851). A third, `_format_unanchored_section`
(line 765, RS≥80-with-no-theme), is even further gone — it isn't just uncalled, it
isn't even passed as a parameter into `_format_evening_briefing` anymore. Grepped the
theme engine for the same predicate under another name (theme-discovery's own
"uncovered stocks" LLM-assignment prompt runs at RS≥50 for a different purpose —
auto-assigning stocks to *existing* themes, not flagging RS≥80 orphans for the
operator) — confirmed no other surface computes this for operator display. **This
signal has no home anywhere today.**

Root cause, from git history: `b6d79a5` (7/17, the original #479 cut) stopped
rendering these sections but *kept the fetch code untouched* and added a
`"detail on demand: /watch · /ideas · /eps · /sugarbabies · /detectors · /fishhook ·
/undercutrally"` footer as the promised compensating pointer. `b0889f0` (7/20, #492)
restored RISING/RECOVERY/ROTATION inline **but deleted that footer** ("drop the dead
on-demand footer") without restoring an equivalent. Since 7/20 the brief has pointed
to **nothing** for any of this — no inline section, no footer, no menu entry (the same
commit also culled the Telegram `/` menu 33→11). The handlers still work if the
operator happens to already know the exact phrase, which is the silent-orphaning
failure mode restated one layer down.

One more of the footer's own citations was already wrong when it was written:
`/eps` routes to `_handle_ep_query` (EP **alerts**), not `_handle_ep_outcomes` (EP
**outcomes**) — the real trigger is the phrase `"ep outcome"` (or `"ep performance"` /
`"ep results"` / etc). `/ideas` was cited for MA pullbacks — `ideas_board.py` never
references `get_ma_pullbacks`; the real trigger is the bare keyword `"pullback"` (or
`"10ma"`/`"20ma"`/etc). `/undercutrally` doesn't exist as a command at all — it was
folded into `/detectors` back on 2026-06-06, before the footer that cited it was
written. **This is why every command in this document's traceability table (§4) was
verified against the actual dispatch table / routing cascade, not carried forward
from the old footer.**

---

## 1. Inventory — the brief as it renders today

Source: `_format_evening_briefing` (briefing.py:1000-1090), cross-checked against 4
real `evening_brief_sent` audit rows (7/21–7/24 prod): **4948 / 5048 / 5203 / 5248
chars.** Telegram's hard limit is 4096 chars/message and `send_telegram_message`
auto-splits — **the evening brief is already 2 Telegram messages every night**,
despite carrying strictly less content than before the 7/17 cut. The "one message"
goal from the original #479 mock was never actually reached, or has regrown past it
since (#492, #493).

| # | Section (as rendered today) | Signal | Typical size | Notes |
|---|---|---|---|---|
| — | Title | date | 1 line | |
| — | v1.0 close-out line | FL-1/3/4/8 clock + blocking count + est. declaration date | 1 line (+blank) | **Stale as of this proposal** — see §0.5 below |
| — | Data-quality warnings | ingest/gap anomalies | 0 lines (rare) | conditional |
| 1 | MARKET CONDITION | regime verdict, net-score, cluster-deterioration alert (fires-only), VIX/EP-filter/size | ~3-4 lines | compacted 7/17 from ~20 |
| — | CRYPTO vs MARKET (#493) | BTC/ETH/SOL vs QQQ/SPY/IWM, 2wk/4wk, verdict | ~4 lines | conditional on fetch success |
| 2 | RS LEADERS | top-10 by RS composite, EPS/earnings flags | ~12 lines | was top-20/30 pre-7/17 |
| 3 | THEME SCORECARD | ecosystem-grouped (#473): up to 7 ecosystems × up to 2 sub-themes each | ~25-30 lines | **verified real data 7/24: 50 active themes (5 Accel/29 Mainstream/16 Nascent), 113 theme→ecosystem mappings** — this bound is doing real work; the *legacy* (non-ecosystem) fallback path has no cap at all and would render all 50 if `eco_map` is ever empty |
| 4 | RISING (velocity) | sustained 2+ week RS acceleration | 0-8 lines | conditional, capped top-6 |
| 5 | RECOVERY | 1M RS high, composite still low (fast V-turn) | 0-12 lines | conditional, capped top-10 — **verified real data 7/24: 69 stocks qualified** the underlying filter, section shows top 10 |
| 6 | ROTATION WATCH (turners) | sector clusters turning from weak, 3+ wk streak | 0-var lines | conditional. **`_format_turners_section` caps tickers-per-cluster at 6 but never caps the NUMBER of clusters** — `get_rs_turners` fetches up to 40 qualifying stocks, and every sector with 2+ of them renders its own 2-line block. This is uncapped in the *current live* code, not just a mock artifact — worth fixing in the same pass (§3 proposes a cap). |
| — | Cooldown footer | top-3 chronic/soonest-expiring theme cooldowns | 1 line | **verified real data 7/24: 17 active cooldowns** — footer shows 3 + "+14 more" |
| — | Closing line | "Do your review..." | 1 line | |

**A fourth finding, orthogonal to §0's "fetched and discarded" list:** `get_rs_velocity`,
`get_rs_turners`, and `get_rs_recovery` (RISING/ROTATION/RECOVERY's data sources) have
**no operator-facing caller anywhere outside `briefing.py`** (verified by grepping every
call site repo-wide — `get_rs_velocity`/`get_rs_turners` are also used internally by
`theme_engine.py`/`theme_synthesis.py` for automatic theme-candidate generation, but
that's engine machinery, not an operator command; `get_rs_recovery` has exactly one
caller, period). **The evening brief is the ONLY place any of these three signals is
visible to the operator, at all.** That changes the stakes for §4's traceability: there
is no drill-down to cite for anything these sections cap out of view — a "see /themes
for more" pointer would be exactly the kind of unverified citation §0 spends three
paragraphs indicting. The mock in §3 says so explicitly instead of inventing a pointer.

**Fetched every night, computed, never rendered, never pointed to** (the §0 finding):
EP outcomes today, 9M sugar babies (daily + persistent cohort), 9M anticipations,
wick-fill telemetry, undercut & rally, MA pullbacks, weekly signal-quality (Fridays),
unanchored RS≥80 leaders.

**Correctly and cleanly retired** (contrast case, not an orphan): Fishhook V3
(undercut-&-reclaim shadow setup) — removed completely in `2b8f346`, operator-approved
2026-07-21, all its params (`fishhook_open_count` etc.) removed from the function
signature too. This is what a clean retirement looks like — the difference from the
§0 list is that here the *fetch* was removed along with the *render*.

### 0.5 — the v1.0 close-out line is now stale, not just uncounted

Not part of the inventory table's "orphaned" bucket — the opposite problem. Prod,
just run:
```
🏁 v1.0: FL-1 10/10 ✓ · FL-3 7/7 ✓ · FL-4 5/5 ✓ · FL-8 4/4 ✓ · blocking 0 open · decl ~7/26
```
All four clocks are already at target, blocking is 0, and it's still printing a
forward-looking "decl ~7/26" **estimate** — but v1.0 was **declared** 2026-07-24 (git
history: `9fdbb57` "🏁 v1.0 DECLARED — §8 signed"). The anti-idle countdown surface did
its job and finished; it doesn't know it finished. This is a fork for the operator
(§6), not something I'm pre-deciding — retiring vs. repurposing to the #419 Phase-2
program status touches what the brief is *for*, not just formatting.

---

## 2. Where sections genuinely overlap — the consolidation candidates

Three merges, each verified against the actual code computing the underlying data
(not just "these sound similar"):

**A. RISING + RECOVERY + ROTATION WATCH → one "RS TURNING" section, 3 sub-lenses.**
All three are read off the *same* weekly-RS-snapshot substrate
(`_prepare_weekly_snapshots` / `mi_stock_scores` week-over-week deltas) — they're not
one signal restated, they're three genuinely different lenses on it (individual
sustained momentum / individual fast V-reversal off a low base / sector-level
clustering of the same delta), so none of them can be dropped. What's redundant is
the **presentation overhead**: 3 independent section headers + 3 blank-line gaps for
content that's conceptually "how is RS moving this week." Folding them under one
header with 3 labeled sub-blocks keeps each lens at its **existing live cap**
(RISING top-6, RECOVERY top-10 — unchanged from today's code) and drops ~4-6 lines of
header/blank padding — it does **not** mean every qualifying ticker is shown; RECOVERY
already truncates 69→10 today and will keep doing so. The one actual behavior change
here is ROTATION: today's `_format_turners_section` has no cap on the number of
sector clusters shown (see §1's finding), so this design adds one — top-3 clusters by
size — which is a real, new demotion of long-tail clusters, not just a formatting
change. Flagged as such, not smoothed over: since none of the three lenses has a
drill-down anywhere else in the system (§1's fourth finding), whatever is capped out
of RECOVERY or ROTATION is capped out of the operator's view entirely, not "one tap
away." The mock states this plainly ("not shown — no drill-down surface today")
instead of inventing a pointer the way the pre-existing footer once did.

**B. `sugar_babies` (daily EOD-confirmed) + `cohort_babies` (persistent Pradeep
cohort) → one "9M / SUGAR BABIES" section.** Verified structurally, not just by name:
the persistent cohort (`mi_sugar_babies_cohort`) is *literally built from* repeated
daily prints (≥3 EOD prints in 180 days) — today's daily confirms are a subset of
what will appear in tomorrow's cohort refresh. Showing them as two independent blocks
(as the pre-7/17 brief did) repeats the same tickers under two headers. One section —
today's prints flagged, cohort membership shown with a 🆕 marker on names that printed
today — carries the same information in one pass.

**C. Wick-fill + Undercut&Rally → fold into the same 5-detector roll-up `/detectors`
already computes.** These were displayed as two standalone inline blocks in the
pre-7/17 brief, while three siblings from the *same* shadow-detector family
(flag-break, support-test, MA-pullback/low-vol-rest) were **never** in the brief at
all — only in `/detectors`. That's an inconsistency, not a design: 5 detectors from
one telemetry framework, 2 of them got brief real estate and 3 didn't, for no
principled reason. `_handle_detectors_query` (agent.py:2325) already computes exactly
this rollup (today + 7d counts, per detector) — mirror its 5-line shape into the
brief as one compact block instead of reinventing 2 of the 5 as bespoke sections.

**Considered and rejected as a merge:** RS LEADERS vs. THEME SCORECARD. They share
tickers (a theme's top RS names appear in both), but they're genuinely different
lenses — individual-stock momentum ranking vs. group/theme rotation — and CLAUDE.md's
Theme Engine is explicitly "bottom-up from price action" (themes emerge from RS
leadership, they don't replace it). Collapsing these would lose the individual-stock
view the operator uses for direct trade ideas. See §5.

---

## 3. Proposed consolidated layout

Design principles: (1) every signal in §1's "fetched, never rendered" list gets
either an inline home or an explicit, **verified** drill-down citation — never
silence; (2) the three merges from §2; (3) v1.0 line — omitted from the mocks below,
pending the operator's ruling in §6 Q1 (the mocks assume "retired," the recommendation,
but this is not decided by this document); (4) restore a comprehensive "detail on
demand" footer, this time citing only commands checked against the current dispatch
table (`agent.py`) and routing cascade — not carried forward from the stale 7/17 footer.

Both mocks below were built from real 7/24 prod data where I could pull it (regime,
RS-leaders top-10, theme/cooldown counts, the RS_1m/composite recovery-filter count)
and plausible illustrative fill-in where a section requires computation I didn't run
live (RS TURNING deltas, 9M/EP/detector counts — the underlying tables exist and are
queried above, but reconstructing their exact daily output requires running the
formatter, which is out of scope for a SELECT-only prod check). **Char counts below
are for these exact mock texts (`wc -m`), not a guarantee of the shipped render** —
verifying the real render against live data is a pre-ship step, not something this
proposal claims to have done.

### Busy day (2026-07-24 conditions: Correcting regime, 50 active themes, 69 Recovery-qualifying names, 17 cooldowns)

```
*Apollo Evening Briefing — 2026-07-24*

*1. MARKET BACKDROP* 🟠 *CORRECTING*
  Net score -1 (3 bullish · 4 bearish)
  VIX 18.6 · filter ≥75 — correcting, exceptional only · size ≈0.75×  ·  `/regime` full matrix
  🪙 Crypto LAGGING (ETH −4.1 / BTC −2.8 vs QQQ +1.2, 4wk)

*2. RS LEADERS* — Top 10 by RS composite
`COAG   RS 100 — Agricultural biotech`
`TRAX   RS 100 — Freight/logistics tech`
`FBRX   RS  99 — Clinical-stage biotech`
`TXG    RS  99 — Genomics instruments`
`ATAI   RS  99 — Psychedelic-derived biotech`
`CDNA   RS  99 — Molecular diagnostics`
`MAN    RS  99 — Staffing services`
`UTZ    RS  99 — Snack foods`
`XNCR   RS  99 — Biopharmaceuticals`
`SYRE   RS  99 — Industrial REIT`
_EPS % = latest qtr YoY | ⬆ = accelerating_

*3. THEME SCORECARD* — 50 active · by ecosystem

*1. BIOT Biotech* — 82 · 14 names · 6 RS80+
  ⚡*GLP-1 follow-on* RS 78 Δ+3.2 — CDNA 99 · XNCR 99 · FBRX 99
  📊*Gene therapy* RS 61 Δ-1.0 — SRPT 71 · BEAM 65
  _+2 more sub-theme(s)_

*2. IND Industrials/Freight* — 74 · 9 names · 3 RS80+
  ⚡*Freight recovery* RS 70 Δ+5.1 — TRAX 100 · JBHT 68
  _+1 more sub-theme(s)_

*3. AGCO Agriculture* — 69 · 5 names · 2 RS80+
  🌱*Ag biotech* RS 66 Δ+8.4 — COAG 100 · CTVA 55

*4. CONS Consumer/Staples* — 64 · 8 names · 2 RS80+
  📊*Snack/packaged food* RS 60 Δ+0.5 — UTZ 99 · HRL 52

*5. PSYC Psychedelic/CNS* — 60 · 4 names · 1 RS80+
  🌱*Psychedelic biotech* RS 58 Δ+11.2 — ATAI 99

*6. REIT Real Estate* — 55 · 6 names · 1 RS80+
  📊*Industrial REIT* RS 53 Δ-2.1 — SYRE 99

*7. STAFF Staffing/Services* — 51 · 3 names · 1 RS80+
  📊*Staffing* RS 51 Δ+1.0 — MAN 99

_+3 more ecosystem(s)  ·  ❔ 6 unmapped  ·  🔻 Fading: Semis rebound · Uranium · Coffee names · Ag inputs · China ADRs  ·  /themes = full board_
⚠️ _Unanchored RS80+ (no theme): `QSFT`, `LNTH`, `WVE`_

*4. RS TURNING* — weekly RS delta, 3 lenses on one substrate (no drill-down exists — this section is the ONLY surface for all 3, §1)
🚀 _Rising (accel, comp≥40, top 6)_
  `CDNA` RS 88 [+9←+6←+3←+1]↑
  `TRAX` RS 91 [+7←+4←+2]
  `FBRX` RS 85 [+6←+5←+1←+2]↑
  `XNCR` RS 82 [+5←+3←+2]
  `SYRE` RS 79 [+4←+2←+1←+1]↑
  `UTZ`  RS 76 [+3←+2]
🔁 _Recovery (1M turn off weak base, top 10 of 69 qualifying)_
  `BMNR` 1M 84 · 3M 60 · comp 39 — Crypto-proxy
  `MSTR` 1M 79 · 3M 55 · comp 41 — Crypto-proxy
  `COIN` 1M 81 · 3M 58 · comp 44 — Crypto exchange
  `RIOT` 1M 77 · 3M 50 · comp 38 — Bitcoin miner
  `MARA` 1M 75 · 3M 48 · comp 36 — Bitcoin miner
  `HOOD` 1M 73 · 3M 52 · comp 42 — Fintech
  `SOFI` 1M 71 · 3M 49 · comp 40 — Fintech
  `CLSK` 1M 78 · 3M 51 · comp 37 — Bitcoin miner
  `IREN` 1M 74 · 3M 47 · comp 35 — Bitcoin miner
  `APLD` 1M 72 · 3M 46 · comp 33 — Data center/AI infra
  _59 more qualify, not shown — no drill-down surface today_
🔄 _Rotation (sector clusters, top 3 by size — new cap, see §2A)_
  *Biotech* (4, 3wk streak) RS avg 61←48 — CDNA, XNCR, FBRX, SRPT
  *Industrials* (3, 3wk streak) RS avg 55←42 — TRAX, JBHT, CHRW

*5. 9M / SUGAR BABIES*
  Today: 2 EOD-confirmed — `ABCD` 12.4M vol +18% · `EFGH` 9.1M +11%
  Anticipation-only (3): `IJKL`, `MNOP`, `QRST`
  Cohort (24 persistent, 6 ripe 🎯2 🌀3 🔧1): `ABCD`🆕 6× · `WXYZ` 5× 🌀 · `LMNO` 4× 🔧
  _full cohort `/sugarbabies` · today's raw detail "show 9m"_

*6. EP OUTCOMES TODAY*
  HIGH: 2 detected → 1 entered (`NVAX` @$14.20 +3.2%) · 1 missed (extended)
  MODERATE: 3 detected · 0 auto-entered (manual only)
  _90d history: "ep outcomes"_

*7. SHADOW DETECTORS* (telemetry, no entries submitted)
  🎯 Flag-break 3 · 🛡 Support-test 1 · 📉 MA-pullback 2 · 😴 Low-vol-rest 0 · 🪤 U&R 1 today
  🪝 Wick-fill 2 today — 30d fill 61% (n=24)
  _full roll-up + per-ticker `/detectors`_

🧊 *Cooldowns:* `TSEM` → Semiconductors 4d ⚠️  •  `KALV` → Biotech M&A 11d  •  `KODK` → Legacy tech 2d  •  +14 more (`show cooldowns`)

detail on demand: `/regime` `/themes` "pullback" "ep outcomes" `/sugarbabies` `/detectors` "wick watch" `/ideas`

_Do your review. Pull up charts. Apply your judgment._
```
**3,932 chars — one Telegram message** (limit 4,096, so **164 chars of margin**),
rendered at the SAME per-lens caps the live code already uses today (RISING top-6,
RECOVERY top-10) plus one new cap this proposal adds (ROTATION top-3 clusters — see
§2A; today's live code has no cluster cap at all). This is the honest number, not the
first draft's: an earlier pass compacted RECOVERY to 3 rows + "+N more" and cited
`/themes` as the overflow pointer — `/themes` renders the theme board, not RS-recovery
data (§1's fourth finding: there is no such command), so that draft both showed less
than today's live section AND pointed to a command that doesn't carry this data. Fixed
here: full live-cap row counts, and overflow stated as genuinely unreachable rather
than pointed at the wrong place.

For comparison, the current LIVE brief — carrying strictly less content than this mock
(no EP outcomes, no 9M, no detectors, no weekly-quality, no unanchored) — ran
4,948-5,248 chars on the 4 most recent nights and already splits into 2 messages,
while this mock (more content) comes in under one message. That gap is **not fully
attributable to this design** — the RS-leaders rows here use invented short
descriptions, missing the real `get_description()` text plus `_eps_flag`
(`EPS+22%⬆`) and `_earnings_flag` (`📅`) suffixes the live section renders per row,
and the theme-scorecard mock's ecosystem/sub-theme names are shorter than some real
ones will be. Some of the gap is real consolidation (removing the stale v1.0 line,
merging 3 section-header/blank-line sets into 1 in §2A, the 9M/detector merges in
§2B/C); some of it is mock-vs-live row width this proposal can't attribute without
running the actual formatter. **164 chars of margin, against an unmodeled per-row
width gap, means Q2 (1 vs. 2 messages) should be read as *likely to fire* on real
data, not a remote edge case** — the pre-ship render check against live data (not
done here, out of scope for SELECT-only prod access) is what actually settles it.
See §6 Q2.

### Quiet day (illustrative: Bull regime, small theme/cooldown counts, nothing firing in 9M/EP/detectors)

```
*Apollo Evening Briefing — 2026-08-03*

*1. MARKET BACKDROP* 🟢 *BULL*
  Net score +2 (5 bullish · 2 bearish)
  VIX 14.2 · filter ≥65 — standard (bull) · size ≈1.00×  ·  `/regime` full matrix
  🪙 Crypto IN LINE (ETH +1.8 / BTC +1.1 vs QQQ +1.4, 4wk)

*2. RS LEADERS* — Top 10 by RS composite
`PLTR   RS  94 — Data analytics`
`APP    RS  92 — Ad tech`
`VRT    RS  90 — Data center infra`
`AXON   RS  89 — Public safety tech`
`ANET   RS  88 — Networking`
`CRWD   RS  87 — Cybersecurity`
`NVDA   RS  86 — Semis`
`MELI   RS  85 — LatAm e-commerce`
`TTWO   RS  84 — Gaming`
`DECK   RS  83 — Footwear`
_EPS % = latest qtr YoY | ⬆ = accelerating_

*3. THEME SCORECARD* — 22 active · by ecosystem

*1. TECH AI/Software* — 71 · 9 names · 4 RS80+
  ⚡*AI infrastructure* RS 74 Δ+1.5 — VRT 90 · ANET 88 · NVDA 86
  📊*Cybersecurity* RS 65 Δ-0.5 — CRWD 87 · PANW 62

*2. CONS Consumer/Discretionary* — 58 · 4 names · 2 RS80+
  📊*Footwear/apparel* RS 58 Δ+2.0 — DECK 83 · ONON 60

_+0 more ecosystem(s)  ·  ❔ 3 unmapped  ·  🔻 Fading: none  ·  /themes = full board_

*4. RS TURNING* — weekly RS delta, 3 lenses on one computation
  _nothing qualifying today — quiet week for acceleration/recovery/rotation_

*5. 9M / SUGAR BABIES*
  Today: none EOD-confirmed · 0 anticipation-only
  Cohort (24 persistent, 2 ripe 🎯0 🌀1 🔧1): `ABCD` 6× · `WXYZ` 5× 🌀
  _full cohort `/sugarbabies`_

*6. EP OUTCOMES TODAY* — none today

*7. SHADOW DETECTORS* (telemetry, no entries submitted)
  🎯 Flag-break 0 · 🛡 Support-test 0 · 📉 MA-pullback 1 · 😴 Low-vol-rest 0 · 🪤 U&R 0 today
  🪝 Wick-fill 0 today — 30d fill 58% (n=19)
  _full roll-up + per-ticker `/detectors`_

🧊 *Cooldowns:* `KODK` → Legacy tech 2d  •  +1 more (`show cooldowns`)

detail on demand: `/regime` `/themes` "pullback" "ep outcomes" `/sugarbabies` `/detectors` "wick watch" `/ideas`

_Do your review. Pull up charts. Apply your judgment._
```
**1,873 chars — comfortably one message.**

Sections 4-7 never disappear outright now (unlike today, where RISING/RECOVERY/
ROTATION silently vanish when empty) — a quiet day states "nothing qualifying" /
"none today" once per merged block instead of 3-4 sections each independently going
missing, which itself is signal (confirms the check ran and found nothing, vs. the
section being silently absent for an unknown reason).

---

## 4. Traceability — every signal in today's brief → its home in the new design

Three columns per advisor guidance: the signal, where it lives, and **how the
operator actually finds it** (inline is self-evident; a command is only a real home
if something visible points to it — the footer, in this design, since `/hud`'s 6
drill-down buttons do NOT cover most of this; see the `/hud` note below the table).
Every command/phrase was checked directly against `agent.py`'s dispatch table
(`_handle_slash_command`) or its keyword-routing cascade (`execute_task`), not
carried from the old footer.

| Signal (today) | New home | Discovery |
|---|---|---|
| Regime verdict + VIX/filter/size | §1 MARKET BACKDROP (inline) | always visible |
| Cluster deterioration alert | §1 (inline, fires-only) | always visible when firing |
| CRYPTO vs MARKET (#493) | §1 MARKET BACKDROP (merged) | always visible |
| RS Leaders top-10 | §2 (inline, unchanged) | always visible |
| Theme scorecard (ecosystem) | §3 (inline, unchanged) | always visible; full board `/themes` |
| RISING (velocity) | §4 RS TURNING → 🚀 sub-block, top-6 (unchanged cap) | always visible (states "nothing qualifying" when empty). **No drill-down for anything beyond top-6 — `get_rs_velocity` has no operator-facing caller anywhere else in the repo (§1's fourth finding).** |
| RECOVERY | §4 RS TURNING → 🔁 sub-block, top-10 (unchanged cap; 69 qualified 7/24, only 10 visible) | same — **same no-drill-down caveat; `get_rs_recovery` has exactly one caller, period** |
| ROTATION WATCH (turners) | §4 RS TURNING → 🔄 sub-block, **top-3 clusters (NEW cap — live code is uncapped, §1)** | same — **same no-drill-down caveat** |
| **UNANCHORED (RS≥80, no theme)** | §3 THEME SCORECARD, one fires-only line (restored inline — see mock) | always visible when non-empty, silent when empty (same "fires-only" pattern as the regime cluster-deterioration alert). **This is the one signal from §0 that had literally no home anywhere before this proposal; given one here rather than left as a flagged gap — operator can reject it (§6, Q4).** |
| Cooldowns | footer (unchanged) | always visible; full list `"show cooldowns"` (existing phrase, unchanged) |
| **EP outcomes today** | §6 EP OUTCOMES (restored inline) | always visible; 90d history via `"ep outcome"` phrase (verified: `agent.py:883`, routes to `_handle_ep_outcomes`) |
| **9M sugar babies (daily EOD)** | §5 9M/SUGAR BABIES (restored inline) | always visible; raw detail via `"show 9m"` / bare `"9m"` (verified: `agent.py:855-856`, `_handle_9m_ep_query`) |
| **9M persistent cohort** | §5 (merged, 🆕 marks today's prints) | always visible; full 30-name list via `/sugarbabies` (verified: dispatch table `agent.py:5467`, still callable — removed from the visible `/` menu in the 33→11 cull but not from dispatch) |
| **9M anticipation-only** | §5 (merged) | always visible |
| **Wick-fill telemetry** | §7 SHADOW DETECTORS (restored, merged with U&R) | always visible; per-ticker 30d via `"wick watch"` (verified: `agent.py:861`, `_handle_wick_query`) |
| **Undercut & Rally** | §7 SHADOW DETECTORS (merged into the 5-detector rollup) | always visible; per-ticker 30d via `/detectors TICKER` (verified: same table `mi_flag_undercut_rally` the old inline section read, `agent.py:2349`) — **note: less row-level detail than the old standalone U&R block** (no base_low→undercut_low, reclaim%, or cohort-flag columns); flagged as a real, accepted loss in exchange for consistency with the other 4 detectors (§5) |
| **Weekly signal quality (Fri)** | §8 (new, Friday-only, not in the mocks above since neither sample date is a Friday) | always visible on Fridays — see design below |
| **MA Pullbacks** | Footer only (`"pullback"` phrase, verified: `agent.py:954`, `_handle_pullback_query`) | **NOT restored inline in this design — flagged as a judgment call, see §5** |
| v1.0 close-out line | **Operator decision pending (§0.5, §6)** | n/a until ruled |

**§8 Weekly signal quality (Friday-only) — not shown in the mocks (neither sample
date is a Friday), proposed shape:**
```
📊 *SIGNAL QUALITY (30d)* — Fridays only
  RS Top20: avg +X.X% vs SPY +X.X% (alpha +X.X%)
  EP alerts: N/M profitable at 1M (XX%)
```
Reuses the already-written (currently dead) `_format_signal_quality_section` verbatim
— zero new formatting code, just re-wiring the call. Adds ~3 lines, Fridays only,
zero cost the other 4 days.

**On `/hud`:** its 6 drill-down buttons (verified in `channels/telegram.py:1473`)
route to `/regime`, `/themes_detail All`, `/eps` (alerts, not outcomes), `/9m`,
`/clusters`, `"show watchlist"`. That covers regime/themes/EP-alerts/9M/watchlist —
it does **not** reach EP outcomes, wick, the persistent sugar-babies cohort, U&R,
pullbacks, or weekly signal-quality. `/hud` is a good front door for what it covers;
it doesn't substitute for the brief's own footer for everything else, which is why
the footer restoration in §3 is load-bearing, not decorative.

---

## 5. What this is NOT proposing, and why

- **Not folding RS LEADERS into THEME SCORECARD.** Considered in §2 — different
  lenses (individual vs. group), CLAUDE.md's theme-engine philosophy treats RS
  leadership as upstream of themes, not redundant with them.
- **Not restoring MA Pullbacks inline.** It's the one signal from the "fetched,
  never rendered" list I'm leaving as footer-only rather than promoting to a section.
  Reasoning: unlike EP outcomes / 9M / detectors, pullback data is inherently a
  *screening* tool (near-MA entries across the whole RS-leader set) that the operator
  pulls on demand when hunting for an entry, not something that needs a nightly push
  — and every other section already competes for space. This is a judgment call, not
  a hard rule; flagged explicitly for the operator to overrule (§6, Q3).
- (UNANCHORED is restored inline in this design — §3/§4 — not on this list. It was
  the most completely orphaned signal found in §0, and per the task's own rule ("if
  any signal has no home, the design is wrong") it gets a home rather than staying a
  flagged gap. §6 Q4 gives the operator the explicit chance to reject it.)
- **Not touching the 16:55 ET Close Digest.** That's the *other* half of the original
  #479 proposal (§1 of the 7/17 doc) and shipped separately (`close_digest.py`) — it's
  live, working, and out of scope for this evening-brief-specific redesign.
- **Not touching the morning briefing.** Separate function, separate schedule, not
  named in this task.
- **Not touching the Telegram `/` menu (33→11 cull) or re-adding entries to it.** The
  discoverability fix here is the brief's own footer, which is always visible whether
  or not a command is in the "/" autocomplete menu. Re-expanding the menu is a
  separate, smaller decision the operator can make independently (§6, Q5).
- **Not changing any detection criterion, safeguard, sizing, or entry/exit logic.**
  Every signal discussed is display-only (regime sizing display, RS/theme scoring,
  shadow-telemetry detectors, EP outcome reporting). THE LINE is untouched.
- **Not fixing the `stage != "Fading"` filter** in `_compute_scored_themes` that
  technically also admits `"Retired"`-stage themes into the "active" scored set
  (observed while reading the code, not requested) — that's theme-engine behavior
  with its own SSoT (`docs/architecture/theme_engine.md`); filed as an observation
  here, not designed around.

---

## 6. Open questions for the operator

1. **v1.0 close-out line** (§0.5): all 4 FL clocks show target-reached, v1.0 was
   declared 2026-07-24, and the line still prints a forward "decl ~7/26" estimate.
   Retire it, or repurpose it to a #419 Phase-2 status line? **Rec: retire — the
   clocks it tracks are the pre-declaration ones; a Phase-2 status line, if wanted,
   is a new design, not a repurposing of this one.**
2. **1 message vs. 2 deliberate messages.** The busy mock above lands at 3,932 chars
   at today's live per-lens caps (164 chars of margin under the 4,096 limit), but the
   mock understates real row width (§3 caption — no real `get_description()` text,
   no EPS/earnings suffixes, illustrative ecosystem names). The current live brief is
   already 4,948-5,248 chars carrying less content. Treat "tips over 4,096 on a real
   busy night" as **likely, not a remote edge case**: is a hard cut acceptable to
   force it under budget, or is a deliberate 2-message split (e.g., split after §3
   Themes) preferable to losing content? **Rec: accept a deliberate split as the
   overflow valve — never a silent cut. Design for 2 messages on busy nights as the
   expected case, 1 message on quiet nights as the bonus, not the other way around.**
3. **MA Pullbacks — footer-only, or promote to an inline section?** (§5). **Rec:
   footer-only, it's a pull tool not a push signal — but flagging since this is the
   one deliberate demotion in an otherwise "everything gets a section" design.**
4. **UNANCHORED (RS≥80, no theme) — restored inline in this design (§3), reversing
   its total absence today.** Ship it as designed, or pull it back out (e.g. if the
   operator judges it noise, or wants it as a command instead of a nightly push)?
   **Rec: ship it — it's the one signal with
   literally nowhere to go today, which is exactly the failure this whole redesign
   exists to prevent.**
5. **Telegram `/` menu (33→11, `b0889f0`).** Independent of this brief redesign —
   worth re-adding any of the demoted commands (`/watch`, `/ideas`, `/wick`,
   `/detectors`, etc.) to the visible menu now that the brief's footer will point to
   them by name, or leave the menu trimmed and rely on the footer + memorized
   phrases? **Rec: leave the menu as-is — the footer restoration is the fix; menu
   real estate is a separate, smaller UX call.**

---

## Summary

- **Sections before:** 10 inline elements render today (title, MARKET CONDITION,
  CRYPTO vs MARKET, RS LEADERS, THEME SCORECARD, RISING, RECOVERY, ROTATION WATCH,
  cooldown footer, closing line) + 1 stale line (v1.0 closeout) + **8 signals fetched
  every night and silently discarded** (7 of them — EP outcomes, 9M daily, 9M cohort,
  9M anticipations, wick, U&R, MA pullbacks — have a real command home, reachable only
  if the operator already knows the exact phrase, since no footer has pointed to any
  of them since 7/20; 1 — weekly signal quality — has no home anywhere in the repo,
  confirmed by grep) + **1 signal (UNANCHORED) that isn't even fetched anymore** — its
  parameter was removed from `_format_evening_briefing`'s signature entirely, and no
  other mechanism in the theme engine surfaces the same population to the operator.
- **Sections after:** 9 inline elements (title, Market Backdrop, RS Leaders, Theme
  Scorecard [+ Unanchored fires-only line], RS Turning, 9M/Sugar Babies, EP Outcomes,
  Shadow Detectors, closing line) + cooldown footer + Friday-only Signal Quality +
  a verified drill-down footer. v1.0 line pending operator ruling (§6 Q1) — removed
  from the count either way, since it's not part of the brief's actual market content.
- **Biggest consolidation win:** the RISING+RECOVERY+ROTATION → RS TURNING merge
  (§2A) — same weekly-RS-snapshot substrate, three real lenses preserved at their
  existing display caps, ~4-6 lines of header/blank overhead removed. (RECOVERY and
  ROTATION still truncate the tail — 69→10 and uncapped→3 clusters respectively —
  but that truncation exists in today's live code too, or is called out as new; it's
  not something this merge introduced.)
- **Signals with NO home anywhere in the current system, found and named loudly (not
  quietly dropped) — both given a home in this design:** (1) UNANCHORED (RS≥80, no
  active theme) — confirmed via grep across the theme engine that no other mechanism
  surfaces this population to the operator; restored as a fires-only line in §3
  (operator can reject, §6 Q4). (2) Weekly signal-quality (RS-alpha-vs-SPY + EP hit
  rate, Fridays) — confirmed via repo-wide grep that `get_weekly_signal_summary` has
  exactly one caller and it discards the result; restored as §8, Friday-only. **Zero
  signals from today's brief are left without a home in this design** — the one
  remaining caveat is RS TURNING's tail (RECOVERY beyond top-10, ROTATION beyond
  top-3): real signal that's genuinely invisible past the cap, with no drill-down
  anywhere in the codebase to point to (§1's fourth finding) — named explicitly in
  the mock rather than smoothed over with an invented pointer.
