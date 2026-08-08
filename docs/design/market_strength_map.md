# Market Strength Map — holistic multi-asset leadership (design SoT)

**Status:** design-in-progress (#494). Slice 1 (crypto-vs-market pulse, #493) shipped 2026-07-20.
**Origin:** operator 2026-07-20 — *"Do we have a holistic view of where strength is? It can be crypto,
healthcare, gold/silver, whatever it is."* This doc is the durable context for the goal so the design
survives across sessions.

## The goal

One holistic, at-a-glance view of **where strength is across the whole market** — an extension of the
RS/theme work, not a crypto-only feature. Answer, in one glance: *which asset classes / sectors /
themes are leading right now, and what is rotating up vs down?* The trigger question was "is BTC/ETH
holding up while equities correct?" — but that is one instance of the general question.

## What we already have (inventory, 2026-07-20)

- **Equity strength — substantial.** The ADR-0032 **ecosystem board** rolls ~9,700 stocks → themes →
  20 ecosystems ranked by breadth-weighted RS (E-CYBR, E-INS, E-CONS…). Plus **ROTATION WATCH**
  (`get_rs_turners` — sectors turning weak→strong), **RISING** (`get_rs_velocity` — sustained accel),
  **RECOVERY** (`get_rs_recovery`, #492 — fast V-turn off a weak base), and **RS leaders**. Metals/energy
  already appear here *as their miner/ETF equities* (the "Precious Metals Miners" theme, Energy names).
- **Crypto — data exists, mostly dark.** Nightly crypto RS module (`crypto/`): top-250-by-mcap ∪
  27-name watchlist, `crypto_rs_scores` (rs_1m/3m/6m/composite, mcap-bucketed), BTC dominance. Gated by
  `CRYPTO_RS_ENABLED` (off) → `/crypto`, `/altseason` hidden.
- **Regime** — market condition + Stockbee breadth (MAs, VIX, T2108), QQQ-centric. No crypto/commodities.

## The gaps (why it doesn't feel holistic yet)

1. **Equity-only frame.** Crypto is a separate silo on its *own* RS scale; metals/oil exist only as
   equities, not as assets.
2. **Fragmented.** Ecosystem scorecard, rotation watch, RS leaders, crypto — four surfaces, no single map.
3. **No cross-asset ranking.** Equity-RS and crypto-RS percentiles aren't comparable, so nothing says
   *"crypto is THE leading asset class right now, vs stocks vs metals."*

## The model (working draft)

A **two-layer map**:

- **Top layer — asset-class leadership.** Equities · Crypto · Metals · Energy · Bonds, each ranked by
  trailing RS vs a common benchmark → *"where's the money going?"* one glance. Slice 1 (crypto-vs-market
  pulse) is the first cell (Crypto vs Equities); add Metals, Energy rows the same way.
- **Middle layer — within the leading class.** For equities: the ecosystem board (have it). For crypto:
  tiered token RS (#492-B). Drill from the strong asset class into what inside it is strong.
- **Rotation woven through both** — "what's turning up/down" at each layer (ROTATION WATCH generalizes).

Surface = evening brief and/or `/hud`. **No new commands** (operator constraint 2026-07-20).

## ⚠ THE CORE OPEN QUESTION — asset ↔ equity mixing (operator, must resolve at design time)

The asset-vs-equity split is **not clean**. A precious-metals move shows up in *both* gold/silver
(the asset) *and* the miners (equities) — and we want to see strength in both, plus their relationship.
Same for crypto ↔ crypto miners/MSTR/COIN, energy/commodities ↔ energy equities, and on down the list.
An equity expression is a **leveraged, higher-beta play on the underlying asset plus idiosyncratic
equity risk** — miners can lead, confirm, or lag the metal, and that divergence is itself signal.

**How do we mix the two? Options to weigh (do NOT decide yet — flesh out in #494):**

1. **Separate** — asset-class RS (gold, crypto, oil) as one layer; equity RS (ecosystem board) as
   another. Simple; loses the link.
2. **Unified** — assets *and* their equity expressions on one common RS/return frame. Shows gold next
   to gold-miners; but conflates different vol/risk profiles on one percentile scale.
3. **Hybrid "complex"** (leading candidate) — a **complex** groups an asset with its equity expression:
   *Precious Metals complex* = {gold, silver, GDX/miner theme}; *Crypto complex* = {BTC/ETH, MSTR/COIN,
   crypto miners}; *Energy complex* = {oil/gas, XLE/E&P}. The map shows the **asset as anchor + the
   equities as the leveraged expression + their divergence** (are miners confirming/leading/lagging the
   metal?). Richest; directly answers "we see gold *and* gold stocks rise — show me both + the relationship."

Open sub-questions for #494: common cross-asset RS frame (trailing-return percentile? vol-adjusted?);
where commodity/asset price series come from (we have crypto closes + equity/ETF closes; spot metals/oil?);
how a "complex" maps onto the existing theme/ecosystem structure; how rotation reads across asset classes.

## ⚠ DATA AVAILABILITY — answered 2026-08-07, BEFORE the design session (it changes the fork)

The doc listed *"where do commodity/asset price series come from (spot metals/oil?)"* as an open
sub-question. **It is answered, and the answer removes a constraint rather than adding one:**

**Every asset class we would want already has a liquid ETF proxy carried in `mi_daily_closes`, with
279 daily bars (2025-06-30 → today, ~13 months) — no new data source, no new ingest, no spot feed.**

| Complex | Asset anchor (have) | Equity expression (have) |
|---|---|---|
| Precious metals | GLD · IAU · SLV · PPLT | GDX · GDXJ · SIL |
| Crypto | 289 tokens in `crypto_daily_closes` (BTC/ETH/SOL scored) | MSTR · COIN · miners (equity RS) |
| Energy | USO · UNG | XLE · XOP |
| Industrial metals | CPER · DBC | COPX · XME |
| Uranium | — | URA |
| Agriculture | WEAT · CORN | — |
| Macro backdrop | TLT (rates) · UUP (dollar) | — |

**Why this matters to the decision:** 279 bars comfortably clears the composite RS window
(40% × 1M + 30% × 3M + 30% × 6M needs ~126 bars), so **option 3 (hybrid complex) is buildable TODAY
on data we already ingest.** The fork is therefore a genuine design choice, not a
choose-what-we-can-afford — which is what it would have been had the answer come back "we have no
metals prices."

**Two caveats to carry into the session, not blockers:**
- 13 months of history means a 6-month RS window has ~7 months of lookback for percentile context.
  Fine for ranking, thin for regime comparison across a full cycle.
- `crypto_daily_closes` has at least one row stamped `1969-12-31` (epoch zero) — a bad row to clean
  before any cross-asset percentile is computed off min/max dates. Cosmetic, but it would silently
  skew a "since inception" frame.

**Deliberately NOT decided here:** which of the three mixing models to adopt, and what the common
cross-asset RS frame should be (raw trailing-return percentile vs vol-adjusted). Gold at 12%
annualised vol and a junior miner at 60% do not belong on one raw percentile scale without a
stated choice — that IS the operator's call and the reason this session exists.

## Findings / evidence (2026-07-20)

- **Crypto IS leading the correction** (trailing return): 4wk BTC +2.0 / ETH +10.1 / SOL +8.0 vs
  QQQ −5.7 / SPY −0.3 / IWM −2.0 (2wk: BTC +1.9 / ETH +5.7 vs QQQ −3.7). ETH out-performing QQQ by ~16pts/4wk.
- Crypto-equity proxies recovering on the short window (rs_1m MSTR 76 / COIN 77 / BMNR 98) but buried in
  composite RS (22/28/40) — surfaced via the new RECOVERY section (#492).
- Crypto token universe is **sound, not "polluted"** (my earlier word was wrong): top-250-by-mcap +
  watchlist, $15M floor, majors scored (BTC/ETH/SOL comp ~58). Real issues = mcap-blind RS ranking
  (micro-caps dominate the leaderboard; `mcap_bucket`/`rs_in_bucket` exist but the default view ignores
  them) + young coins NULL composite (HYPE has 174 bars, ~1wk short of the 6-mo window). → #492-B.

## Phased slices + status

- **Slice 1 — crypto-vs-market pulse (#493): SHIPPED 2026-07-20** (evening brief, under regime).
- **#492-B — crypto-token depth:** tiered (bucketed) RS + partial-history composite fallback (un-shadow after).
- **#491 — theme thesis-drift:** stale-identity anchoring (crypto-miner → neocloud).
- **#494 — full design:** the asset↔equity mixing decision + the top asset-class layer + Metals/Energy
  rows + how it all drills into the ecosystem board. **Design-first before building further slices.**

## Related

PLAN.md project "Market Strength Map — holistic multi-asset leadership"; ADR-0032 (theme ecosystems);
`briefing.py::_format_crypto_pulse_section`, `db.py::get_crypto_vs_market_pulse`.
