# EP Trading Rules — Qullamaggie-Style Gap Trading

> Apollo's complete ruleset for Episodic Pivot (EP) gap trades.
> Used by both the backtester and live execution flow.

---

## 1. Pre-Trade Filters

All filters must pass before a trade is considered:

| Filter | Threshold | Rationale |
|--------|-----------|-----------|
| EP Score | >= 70 (HIGH tier) | Quality gate — combines gap %, volume, catalyst |
| ADV Dollar Volume | >= $1M median 20-day | Liquidity — ensures clean fills |
| ATR% (14-day) | <= 15% | Volatility cap — avoids penny-stock chaos |
| Market Cap | >= $500M | Institutional interest floor |
| Market Regime | Not "bear" (advisory) | Trend alignment — logged but not hard-blocked |

## 2. Entry Rules — Opening Range Breakout (ORB)

### Opening Range
- **Definition:** High and low of the first 5-minute bar (9:30-9:35 ET)
- ORB High = first bar's high
- ORB Low = first bar's low

### ATR Stop Width Validation
- If `ORB range (high - low) > 1.5 × 14-day ATR` → **skip trade** (reason: `stop_too_wide`)
- Risk/reward doesn't work when the opening range is too volatile

### Breakout Entry
- Walk 5-min bars after the opening range
- **Entry trigger:** Bar high exceeds ORB High
- **Entry price:** ORB High (breakout level, not bar's high)
- **Initial stop:** ORB Low

### Re-Entry After Stop
- If stopped out intraday, re-enter when bar closes above ORB High
- New stop = re-entry bar's low
- **Maximum 3 entry attempts** per day
- No entry if ORB High never broken → skip (reason: `orb_no_breakout`)

## 3. Day 1 EOD Handling

- **Hold full position** through Day 1 close
- No partial selling on Day 1
- Hard stop (ORB Low) remains active via bar-low check

## 4. Position Management — Day 2+

### Hard Stop Floor
- `hard_stop = Day 1 intraday low` (lowest low across all 5-min bars)
- Never raised, never lowered — absolute floor protection
- Triggered when `bar_low <= hard_stop` → exit at hard_stop price

### 10/20 SMA Trailing Stop
- **Active SMA selection:**
  - If 10-SMA > 20-SMA → use 10-SMA (strong uptrend)
  - Otherwise → use 20-SMA (weaker trend, wider trail)
- **SMA trail only active** when active_sma > hard_stop
- **Exit trigger:** Daily **close** below the effective stop
- **Warm-up:** Need 20+ daily closes for full SMA. If < 20, fall back to hard stop only.

### Effective Stop Calculation
```
effective_stop = max(hard_stop, active_sma, entry_price if breakeven_active)
```

## 5. Partial Profit — Day 3-5

| Day | Action |
|-----|--------|
| Day 1-2 | Hold full position |
| Day 3-4 | Sell 1/3 **only if in profit** (close > entry price) |
| Day 5 | Sell 1/3 **regardless** of profit |

- **After partial:** Move stop floor to breakeven (entry price)
- Breakeven floor participates in effective stop calculation
- Exit reason: `partial_profit`

## 6. Exit Reasons

| Reason | Trigger | Price |
|--------|---------|-------|
| `stop_hit` | Bar low <= hard_stop (Day 1 or Day 2+) | Hard stop price |
| `partial_profit` | Day 3-5 partial take | Bar close |
| `sma_trail_stop` | Daily close < effective stop | Bar close |
| `data_ended` | Ran out of price data | Last close |

## 7. Skip Reasons

| Reason | Trigger |
|--------|---------|
| `orb_no_breakout` | Price never exceeded ORB High on Day 1 |
| `stop_too_wide` | ORB range > 1.5× ATR-14 |
| `adv_too_low` | Dollar volume < $1M |
| `adv_no_data` | No volume data available |
| `atr_too_high` | ATR% > 15% |
| `mcap_too_low` | Market cap < $500M |
| `data_unavailable` | No intraday bars for Day 1 |
| `no_valid_entry` | Day 1 simulation returned nothing |

## 8. Risk Safeguards

- **Max concurrent positions:** 5
- **Max daily new trades:** 3
- **Max sector concentration:** 40%
- **Max portfolio heat:** 20% of account
- **Position size:** Fixed dollar amount (default $10K)

## 9. Backtester Implementation

Files: `agents/market_intelligence/backtester/`
- `filters.py` — Pre-trade filters + `compute_atr_14()`
- `engine.py` — Day 1 ORB sim + Day 2+ SMA trail sim
- `models.py` — `BacktestTrade` with `orb_high`, `orb_low`, `atr_14`, `breakeven_stop`
- `report.py` — Text report + CSV export
- `intraday.py` — Polygon 5-min bar fetcher
- `safeguards.py` — Position/risk limits

---

## Version History

| Date | Change |
|------|--------|
| 2026-03-27 | v2: ORB entry, ATR stop validation, 10/20 SMA trail, delayed partial profit |
| 2026-03-19 | v1: Buy at open, day-low ratchet trail, EOD Day 1 partial |
