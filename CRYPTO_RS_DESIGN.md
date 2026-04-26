# Crypto RS Module — Design Sketch

**Status:** Idea / design only. Not implemented. Awaiting review.
**Created:** 2026-04-26
**Branch:** `claude/crypto-rs-analysis-qjCDl`

## Goal
Track crypto coins showing relative strength vs Bitcoin in preparation for the next alt-season cycle, **without polluting the current equity-focused system**. Surface on-demand + automatic trigger when BTC dominance breaks down.

## Guiding constraints
- **No paid data** at this stage. Free tiers only until alt season confirms.
- **No scheduled Telegram noise** until BTC dominance trigger fires. Default state = silent.
- **Isolated** from existing equity tables / scheduler / agents — clean extraction path later.
- Mirror equity-side methodology where it transfers (RS composite weights, scheduler patterns, audit/error handling).

## Cycle context
Bitcoin halving was April 2024. Historical alt-season window peaks 12–18 months post-halving → roughly Q2–Q4 2026. Building infra now in dormancy phase, ready when rotation kicks in.

---

## Data sources — Multi-tier $0 architecture

**Critical constraint:** Apollo's prod VPS is in Ashburn, VA. **Binance public REST blocks US IPs (403)** — Binance.US has worse coverage and is not a substitute. Architecture below distributes load across US-safe sources, each picking the data band it does best.

| Source | Role | Coverage band | Rate limit | Cost |
|---|---|---|---|---|
| **Kraken REST** (`/0/public/OHLC`) | Majors price feed | BTC, ETH, SOL + top ~50 large/mid caps | Generous public limit | $0 |
| **DexScreener API** | Long-tail price feed | $15M–$500M on-chain (DEX-listed) — KNX, COPPERINU, FARTCOIN, MOG, KTA, VVV bands | 300 calls/min | $0 |
| **CoinGecko (weekly only)** | Universe + categories taxonomy | All top 250 + pre-tagged "AI & Big Data", "DePIN", "Solana Ecosystem", "Meme", etc. | 30 calls/min, 10K/mo | $0 |
| **DefiLlama API** | Macro stablecoin flows trigger | Total stablecoin mcap, USDT/USDC supply curves | No publicly stated limit (be conservative) | $0 |
| **Coinbase REST** (fallback) | Backup majors feed if Kraken outage | Same as Kraken | Generous public limit | $0 |
| ~~Binance~~ | ~~Rejected~~ | US IP blocked | — | — |
| ~~Polygon Crypto~~ | ~~Rejected~~ | Separate sub from stocks; gap on long-tail | — | — |
| ~~CoinMarketCap~~ | ~~Rejected~~ | Free tier excludes historical OHLCV | — | — |

### Source-of-truth allocation
- **Kraken handles ~50 majors** (BTC, ETH, SOL, ADA, DOT, LINK, ATOM, SUI, BNB if listed, ENA, AERO if listed, etc.)
- **DexScreener handles ~200 long-tail** (everything Kraken doesn't list, addressed by `(chain, contract_address)` pair to bypass impostor matching)
- **CoinGecko refreshes weekly** for taxonomy/categories metadata only — no daily price calls (respects 30/min limit cleanly)
- **DefiLlama once daily** for stablecoin total mcap snapshot

### DexScreener data quality gate
DEX data has higher noise (wash trading, impostor contracts, bridge versions). Mitigations:

- **Watchlist coins**: hardcode `(chain, contract_address)` in seed migration. Bypass any symbol/name lookup.
- **Universe-discovery beyond watchlist**: restrict queries to trusted chains only — `ethereum`, `solana`, `base`, `arbitrum`. Apply existing wash-trade gate (vol/mcap ratio + 7d median + 90d age) on top of DS results.
- **Cross-source verification** (cheap sanity check): if a coin is on both Kraken AND DexScreener, prefer Kraken price; if DS price diverges > 5% from Kraken's, flag the DS quote as suspect.

---

## Module layout
Inside existing market agent — no new Docker service, reuses Telegram/audit/DB infra:

```
agents/market_intelligence/crypto/
  kraken_client.py     # Majors REST + OHLC
  dexscreener_client.py # Long-tail (chain, contract_address) lookups + universe scan
  coingecko_client.py  # Weekly taxonomy + universe metadata (rate-limit-aware)
  defillama_client.py  # Stablecoin total mcap ONLY (/stablecoins endpoint)
  coingecko_global.py  # /global endpoint for BTC.D + total mcap (TOTAL3 derived)
  data_router.py       # Decides which source for which coin (Kraken-first, DS fallback)
  rs_engine.py         # RS vs BTC composite
  triggers.py          # Stablecoin + BTC.D + TOTAL3 three-signal trigger
  categories.py        # CoinGecko category sync
  db.py                # crypto_* table queries
  briefing.py          # /crypto formatters
```

Clean extraction path later if it grows into its own sub-agent.

---

## Schema (all `crypto_*` prefix — no `mi_*` collision)

| Table | Purpose |
|---|---|
| `crypto_universe(coin_id, symbol, name, mcap_rank, mcap_usd, last_seen)` | Daily snapshot of top 250 by mcap |
| `crypto_daily_closes(coin_id, date, close_usd, close_btc, volume_usd, mcap_usd)` | `close_btc = close_usd / btc_close_usd` computed at ingest |
| `crypto_rs_scores(coin_id, score_date, rs_1m, rs_3m, rs_6m, rs_composite, mcap_bucket, rs_in_bucket, rs_overall)` | RS scoring output |
| `crypto_categories(coin_id, category_slug)` | Many-to-many from CoinGecko |
| `crypto_category_strength(category_slug, score_date, member_count, median_rs, top3_coins)` | Theme strength by median RS |
| `crypto_btc_dominance(date, dominance_pct, btc_price, total_mcap_usd, slope_30d)` | Daily BTC.D + slope (**CoinGecko `/global`**) |
| `crypto_total3(date, total3_mcap_usd, slope_30d, sma_90d)` | Daily TOTAL3 derived from CoinGecko `/global`: `total_mcap × (1 − btc_pct/100 − eth_pct/100)` |
| `crypto_stablecoin_flows(date, total_stable_mcap, usdt_mcap, usdc_mcap, slope_30d)` | Daily stablecoin mcap (**DefiLlama `/stablecoins`**) — capital-inflow signal |
| `crypto_dominance_alerts(triggered_at, btc_d_pct, total3_breakout, stable_slope_30d, alert_type, cooldown_until)` | Trigger fire log |
| `crypto_watchlist(coin_id, symbol, chain, contract_address, added_at, source, notes)` | User-curated tracked coins; exempt from liquidity floor. `chain`+`contract_address` allow DexScreener direct lookups. |
| `crypto_token_address(coin_id, chain, contract_address)` | Many-to-many bridge between CG `coin_id` and DexScreener `(chain, addr)` for cross-source dedup. |

---

## RS methodology

- **Composite**: 40% × 1M + 30% × 3M + 30% × 6M (mirrors equity side exactly)
- **Numerator**: `close_btc` price series, **NOT** `close_usd`. Coin up 5% vs USD while BTC up 8% = losing alt. This is the entire point.
- **Percentile rank**: within market cap bucket AND overall. Surface both.
  - Bucketed catches micro-cap rotation early without drowning in beta noise.
  - Overall is the headline number.
- **Mcap buckets**:
  - **Mega** (>$50B) — BTC, ETH only most cycles
  - **Large** ($5B–$50B) — top ~20
  - **Mid** ($500M–$5B)
  - **Micro** ($50M–$500M) — where most "very tiny" tracked names live
  - Sub-$50M excluded UNLESS on watchlist (liquidity / wash-trade risk)
- **Liquidity floor**: 24h vol ≥ $5M (lower than equity since crypto is 24/7 continuous). Watchlist override.
- **Universe size**: top 250 by mcap + watchlist union ≈ 250–280 coins.

---

## Theme/category strength

CoinGecko hands us free pre-tagged taxonomy → **skip the entire LLM theme-discovery layer** from equity side.

Per-category daily metric: **median RS of members** (resistant to 1-coin outliers). Telegram surface ranks categories by median RS so "AI is hot, privacy is dead" reads at a glance.

---

## Alt-season trigger — three-signal framework

Each signal answers a **distinct** question. Single-signal triggers (e.g., BTC.D alone) generate false positives because they conflate them.

| Signal | Question answered | Source |
|---|---|---|
| **Stablecoin total mcap** | Is *fresh capital* entering the crypto ecosystem at all? Rising stable supply = USD on-ramp activity. | DefiLlama `/stablecoins` |
| **BTC dominance (BTC.D)** | Of capital already inside crypto, is it rotating *out* of the core? | CoinGecko `/global` |
| **TOTAL3** (total mcap minus BTC + ETH) | Is rotation reaching the *long tail* beyond ETH, or is it stopping at ETH? | Derived nightly from CoinGecko `/global` |

**Why all three (not stables alone, not BTC.D alone):** Stable supply can grow while capital piles into BTC (2024 ETF inflows: stable supply ↑, BTC.D ↑, alts bled). BTC.D can fall purely from BTC → ETH rotation (TOTAL3 flat). Both alone produce false positives that collapse to zero with the third gate.

Daily compute. **All four conditions must hold** to fire:

1. **(1)** Stablecoin total mcap 30d slope **positive** ← capital entering ecosystem
2. **(2)** BTC.D 30d slope **negative** for 5+ consecutive sessions AND BTC.D < **55%** ← rotating out of core
3. **(3)** TOTAL3 30d slope **positive** for 5+ consecutive sessions AND TOTAL3 > **90d SMA** ← reaching long tail
4. **(4)** Last alert ≥ **30 days** ago (cooldown — prevent flapping at thresholds)

On fire:
- Telegram alert with all three signal values
- Auto-attach current top-10 RS-vs-BTC list
- Auto-attach top 3 categories by median RS
- System flips into "alt rotation watch" state — could later promote to higher cadence (weekly digest) automatically.

### Optional pre-arm signal (telemetry only, no fire)
"**Capital arriving but not rotating yet**" = (1) holds, (2) and (3) don't. This is the early-warning state — surface in `/altseason` command to show "stables flowing in, BTC-dominant rally underway, alts not yet rotating." Useful for awareness without firing the full alert.

---

## Wash-trade gate (with $15M micro floor)

The original $50M floor was tightened to **$15M** to natively catch user's smaller tracked coins. Lowering the floor opens the door to wash-traded scams that fake volume to game RS rankings. Three filters in order, all cheap:

1. **Volume-to-mcap ratio sanity**: `0.01 < vol_24h / mcap < 5.0`. Real coins live in 0.05–1.0 range; wash trades show 5x+ (volume exceeds market cap repeatedly = mathematically impossible without churn).
2. **Trading age ≥ 90 days**: kills new-launch pumps. CoinGecko returns `genesis_date` / first-listed date.
3. **7d median volume ≥ $10M**: point-in-time $15M can be a single-day pump. Median over 7d removes flash-volume tokens.

**Watchlist coins bypass all three** (manual override = trust the user). Sub-$15M watchlist coins are tracked but flagged "below universe floor" in surfaces.

---

## Cadence

| When | What |
|---|---|
| **Nightly 6:00 PM ET** | Refresh universe, pull OHLC (Kraken majors + DexScreener long-tail current snapshot), recompute RS, pull CG `/global` (BTC.D, total mcap → derive TOTAL3), pull DefiLlama `/stablecoins`, check trigger. ~50 Kraken calls + ~200 DexScreener calls + 1 CG `/global` + 1 DefiLlama call. |
| **Weekly Sunday** | Refresh CoinGecko categories metadata (low churn). |
| **On-demand otherwise** | No scheduled Telegram output until dominance trigger fires. |

---

## Telegram surface

```
/crypto                  → top 10 RS vs BTC (with mcap bucket tag) + BTC.D + arrow
/crypto AI               → top RS within "AI & Big Data" category
/crypto privacy          → top RS within "Privacy Coins"
/crypto SOL              → SOL profile: 1m/3m/6m RS, categories, mcap bucket, RS-in-bucket rank
/crypto add SOL          → watchlist add
/crypto watchlist        → your tracked coins with current RS, sorted
/altseason               → BTC.D current/slope/threshold, trigger status (armed/fired/cooldown)
```

---

## Free-tier budget check

- Daily ingest: ~50 Kraken (no limit) + ~200 DexScreener (300/min limit ≈ 40s of throttled calls) + 1 CG `/global` + 1 DefiLlama call.
- CoinGecko load: 1 call/day for `/global` macro = 30/month. Plus weekly category refresh (~250 calls in one burst, takes ~10 min at 30/min limit) ≈ 1000/month. Plus one-time backfill (~280 calls).
- **Total CG ~1100/month steady-state** — well under the 10K free-tier cap; ample headroom for `/crypto SYMBOL` interactive queries and new universe entrants.

---

## Out of scope (deliberate, defer until alt season actually fires)

- Intraday setup detection (24/7 market needs different model — VWAP/range concepts don't map cleanly)
- On-chain metrics (Glassnode = paid)
- Social sentiment (LunarCrush = paid)
- Trading execution (no broker integration; this is RS surveillance only)
- EP-equivalent breakout detection — revisit when intraday infra justified

---

## Watchlist seed (27 coins)

User-provided 2026-04-26. To be inserted into `crypto_watchlist` on first migration. All meme/Solana ecosystem tickers pinned by **CoinGecko ID** (not symbol match) to prevent impostor-token collisions.

| Symbol | Name | Theme(s) | Bucket | Notes |
|---|---|---|---|---|
| BNB | Binance Coin | Layer 1 / CEX | Mega | |
| SOL | Solana | Layer 1 / Solana | Mega | |
| ADA | Cardano | Layer 1 | Large |  |
| DOT | Polkadot | Layer 1 | Large |  |
| LINK | Chainlink | Oracle / DeFi infra | Large |  |
| HYPE | Hyperliquid | DeFi (perp DEX) | Large |  |
| ATOM | Cosmos | Layer 1 | Mid |  |
| SUI | SUI | Layer 1 | Mid |  |
| TAO | Bittensor | AI / L1 | Mid |  |
| RENDER | Render | AI / DePIN | Mid |  |
| FET | ASI Alliance | AI | Mid | Formerly Fetch.ai (merged AGIX + OCEAN) |
| ENA | Ethena | DeFi (synth-yield) | Mid |  |
| AERO | Aerodrome | DeFi / Base L2 | Mid |  |
| VIRTUAL | Virtuals Protocol | AI (agent infra) | Mid |  |
| PEPE | Pepe | Meme / ETH | Mid | Pin by CG id |
| BONK | Bonk | Meme / Solana | Mid | Pin by CG id |
| AKT | Akash Network | AI / DePIN | Mid–Micro |  |
| ASTER | Aster | DeFi | Mid | User's ticker showed perp (`.P`); spot RS uses CG id |
| SYRUP | Maple Finance | DeFi / RWA-yield | Micro |  |
| CAKE | PancakeSwap | DeFi / BSC | Micro |  |
| PUMP | Pump.fun | Solana / launchpad | Micro |  |
| MOG | MOG Coin | Meme / ETH | Micro | Pin by CG id |
| FARTCOIN | Fartcoin | Meme / Solana | Micro | Pin by CG id |
| VVV | Venice Token | AI (inference) | Micro–below floor |  |
| KTA | Keeta | Layer 1 (newer) | Below floor | New L1, watchlist override |
| COPPERINU | Copper Inu | Meme | Below floor | Watchlist override |
| KNX | KnoxNet | Unclassified | Below floor / DEX-only | **May not be on CoinGecko** — needs DexScreener fallback or manual tracking |

**Theme distribution:**
- **AI / DePIN (7):** TAO, RENDER, AKT, FET, VIRTUAL, VVV, (KTA?) — heaviest cluster
- **Layer 1 (6):** BNB, SOL, ADA, DOT, ATOM, SUI
- **DeFi (7):** ENA, AERO, SYRUP, CAKE, HYPE, ASTER, LINK
- **Memes (6):** PEPE, PUMP, BONK, MOG, FARTCOIN, COPPERINU
- **Solana ecosystem cross-tag (4):** SOL, PUMP, BONK, FARTCOIN — deliberate cycle bet

**Data-sourcing risks** (verify on first ingest):
- KNX (KnoxNet) — DEX-only Ethereum pair; likely not on CoinGecko. If missing → DexScreener fallback or drop from automation.
- COPPERINU — may not be on CoinGecko. Same fallback path.
- KTA, VVV — newer; CoinGecko may have them but verify.
- ASTER ticker disambiguation — user's source showed perpetual contract (`ASTERUSDT.P`); we want spot.

---

## Closed design questions

1. ~~**Polygon crypto coverage check**~~ → **Resolved 2026-04-26**: Polygon Crypto is a separate subscription (not bundled with Stocks). Free tier = 5 req/min, EOD only. Coverage gap on Solana ecosystem / DEX-only / new launches makes it unfit for the long-tail tracking goal. Subsequently superseded by full architectural pivot — see "Data sources" section above. Final stack: Kraken (majors) + DexScreener (long-tail) + CoinGecko (taxonomy + `/global` macro) + DefiLlama (`/stablecoins` only).
2. ~~**Watchlist seed**~~ → **Resolved 2026-04-26**: 29 coins provided (table above).
3. ~~**Dominance threshold**~~ → **Resolved 2026-04-26**: BTC.D 55% retained, AUGMENTED with TOTAL3 dual-trigger (see "Alt-season trigger" section above) to eliminate BTC→ETH rotation false positives.
4. ~~**Bucket boundaries**~~ → **Resolved 2026-04-26**: Micro floor lowered $50M → **$15M**, paired with three-filter wash-trade gate (vol/mcap ratio, 90d age, 7d median vol). Watchlist coins exempt from all gates.

## CoinMarketCap evaluation (closed)

**Rejected 2026-04-26.** Free Basic tier (10K credits/month, 30 req/min) explicitly excludes historical OHLCV — only Startup tier ($79/mo) unlocks it. Without historical bars, multi-timeframe RS (1m/3m/6m) is impossible. Categories endpoint IS in free tier (could substitute for CoinGecko's), but not enough on its own to justify the dual-source complexity.

---

## Migration path when going live (post-trigger)

- Upgrade to CoinGecko Pro ($129/mo) for higher rate limits + faster refresh
- Add intraday OHLC for setup detection
- Consider EP-equivalent for crypto (24/7 model design needed)
- Possibly broker integration (Coinbase Advanced / Kraken API)
