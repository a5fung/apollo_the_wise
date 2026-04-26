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

## Data sources (all free)

| Source | Use | Notes |
|---|---|---|
| **CoinGecko free** | Universe + market cap rankings + **categories** (their pre-tagged taxonomy) | 30 calls/min, ~10K/month. Categories = killer feature: "AI & Big Data", "Privacy Coins", "DePIN", "Meme", "RWA", "Layer 1", "Solana Ecosystem", etc. Many-to-many tags. |
| **Binance public REST** (`/api/v3/klines`) | Primary OHLC for ~150 of top 250 coins via USDT pairs | Free, no key, no rate limit issues at this scale. |
| **CoinGecko `/market_chart`** | Fallback OHLC for coins not on Binance | Some privacy coins, some Solana ecosystem alts. |
| **Polygon crypto** | TBD — coverage check pending | Already paid; if coverage is good, drop CoinGecko price calls. |

---

## Module layout
Inside existing market agent — no new Docker service, reuses Telegram/audit/DB infra:

```
agents/market_intelligence/crypto/
  data_source.py     # CoinGecko + Binance clients (free tier rate-limited)
  rs_engine.py       # RS vs BTC composite
  dominance.py       # BTC.D tracker + trigger logic
  categories.py      # CoinGecko category sync
  db.py              # crypto_* table queries
  briefing.py        # /crypto formatters
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
| `crypto_btc_dominance(date, dominance_pct, btc_price, total_mcap_usd, slope_30d)` | Daily BTC.D + slope |
| `crypto_dominance_alerts(triggered_at, dominance_pct, slope_30d, alert_type, cooldown_until)` | Trigger fire log |
| `crypto_watchlist(coin_id, added_at, source, notes)` | User-curated tracked coins; exempt from liquidity floor |

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

## Alt-season trigger — dual signal (BTC.D + TOTAL3)

BTC.D alone is a muddy signal: it can drop purely from BTC → ETH rotation (e.g., BTC.D 55→50% while ETH.D goes 18→23%), with zero capital flowing into the long tail. **TOTAL3** (total crypto market cap minus BTC and ETH) eliminates this false positive — it only rises when capital actually flows into alts beyond ETH.

Daily compute. **All five conditions must hold** to fire:

1. **(A)** BTC.D 30d slope negative for 5+ consecutive sessions
2. **(B)** BTC.D absolute < 55% (last cycle's alt-season-confirm level; configurable)
3. **(C)** TOTAL3 30d slope positive for 5+ consecutive sessions
4. **(D)** TOTAL3 > 90d SMA (operational definition of "broken out of multi-month base")
5. **(E)** Last alert ≥ 30 days ago (cooldown — prevent flapping)

C+D together encode the breakout cleanly: positive momentum AND already above the 3-month average. C alone fires too early on noise; D alone fires at the top of a base about to roll over. Both = real capital rotation.

On fire:
- Telegram alert
- Auto-attach current top-10 RS-vs-BTC list
- Auto-attach top 3 categories by median RS
- System flips into "alt rotation watch" state — could later promote to higher cadence (weekly digest) automatically.

**New schema for TOTAL3:** `crypto_total3(date, total3_mcap_usd, slope_30d, sma_90d)` alongside `crypto_btc_dominance`. One row/day, computed at nightly ingest from `sum(top_250_mcap) - btc_mcap - eth_mcap`.

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
| **Nightly 5:30 PM ET** | Refresh universe, pull OHLC, recompute RS, update dominance, check trigger. ~250 Binance calls + ~50 CG fallback + 1 dominance call. |
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

- Daily ingest: ~250 Binance calls (no limit) + ~50 CoinGecko `/market_chart` fallback = 50 CG calls/day ≈ 1500/month → well under 10K cap
- Weekly category refresh: ~250 calls in one burst (rate-limited to 30/min, takes ~10 min) ≈ 1000/month
- **Total CG ~2500/month** — comfortable headroom for `/crypto SYMBOL` interactive queries.

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

1. ~~**Polygon crypto coverage check**~~ → **Resolved 2026-04-26**: Polygon Crypto is a separate subscription (not bundled with Stocks). Free tier = 5 req/min, EOD only. Coverage gap on Solana ecosystem / DEX-only / new launches makes it unfit for the long-tail tracking goal. **Decision: stick with Binance + CoinGecko free combo.**
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
