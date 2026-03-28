# EP Trading Rules

> Apollo's ruleset for Episodic Pivot (EP) gap trades.
> Used by both the backtester and live paper tracker.
>
> Rules are split into **Qullamaggie's core rules** (sourced directly from
> qullamaggie.com) and **Apollo additions** (our own extensions where he
> says "create your own rules" or doesn't specify).

---

## Part A — Qullamaggie's Core Rules

*Sources: qullamaggie.com/how-to-master-a-setup-episodic-pivots/ and
qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/*

### A1. What qualifies as an EP

- Gap up **10%+** on earnings or a similarly significant catalyst
- **"Big volume. If the volume is not there in premarket, it needs to come in at the open."**
- **"Big growth numbers, preferably mid/high or even triple digit EPS and revenue growth and a significant beat to analyst expectations."**
- **"It's best if the stock has not rallied over the past 3-6 months."**
- Avoid repeat EPs on the same stock — **"failure rate is higher"**

### A2. Entry

- **"Enter opening range highs. ORH can be the highs of the first 1-, 5-, or 60-minute candle."**
- Entry price = the ORH breakout level

### A3. Stop

- **"The stop is at the lows of the day."**
- This means the lowest price printed so far at the time of entry — which is the opening range low when entering on an ORH break early in the session.

### A4. ATR stop validation

- **"Make sure your stop is no more than 1x, or maximum 1.5x the average daily range or the average true range."**
- If the distance from entry to stop exceeds this, pass on the trade.

### A5. Trailing stop

- **"Trail your stop with the 10- or 20-day moving average once they surpass your initial stop."**
- Exit on first daily close below the active MA.
- He also says: **"Create your own sell rules. You can trail these with the 20- or 50-day moving average, or whatever you find to work the best."**

### A6. Position sizing

- General guidance: **0.25–1% account risk per trade**, max 30% of account in one position.
- No EP-specific sizing formula given.

### A7. What he does NOT specify

These are areas where he explicitly leaves it open or doesn't address:
- Day 1 EOD handling (partial sell vs hold full)
- Re-entry after being stopped out intraday
- Exact partial profit timing / percentage
- Breakeven stop mechanics
- Whether to use 10 vs 20 SMA (he says "10- or 20-day")

---

## Part B — Apollo Additions

*Our extensions for areas Qullamaggie leaves open. These are backtested
and refined over time — not gospel.*

### B1. Opening Range = 5-minute bar

We use the first 1-min bar (9:30–9:31 ET) as the opening range.
Qullamaggie mentions 1-min, 5-min, or 60-min — we use 1-min to get
the tightest ORB and avoid the ATR filter rejecting big-gap EPs
where the first 5 minutes are naturally volatile.

### B2. Re-entry after stop-out (Day 1)

- If stopped out intraday, re-enter when a bar's high breaks above ORB High
- **Stop stays at ORB Low** for all attempts (consistent with "lows of the day")
- Maximum 2 entry attempts per day (1 initial + 1 re-entry)
- If ORH never broken → skip (`orb_no_breakout`)

### B3. Day 1 EOD

- Hold full position through close — no partial selling on Day 1
- Rationale: Qullamaggie's best EPs run for days/weeks. Day 1 partials cut winners early.

### B4. SMA selection logic

- Use 10-SMA when 10 > 20 (strong uptrend, tighter trail)
- Use 20-SMA otherwise (wider trail for weaker trends)
- SMA trail only activates once it surpasses the hard stop floor
- Warm-up: need 20+ daily closes; if fewer, hard stop only

### B5. Partial profit — Day 3-5

| Day | Action |
|-----|--------|
| Day 1-2 | Hold full position |
| Day 3-4 | Sell 1/3 only if in profit (close > entry price) |
| Day 5 | Sell 1/3 regardless |

- After partial → move stop floor to breakeven (entry price)
- Breakeven participates in effective stop: `max(hard_stop, active_sma, entry_price)`

### B6. Hard stop floor (Day 2+)

- `hard_stop = Day 1 intraday low` (lowest low across all 5-min bars)
- Never raised, never lowered — absolute floor
- Triggered on `bar_low <= hard_stop` → exit at hard_stop price

---

## Part C — Pre-Trade Filters (Apollo)

| Filter | Threshold | Source |
|--------|-----------|--------|
| EP Score | >= 70 (HIGH tier) | Apollo MAGNA53 model |
| Gap % | >= 8% (scoring penalizes 8-9%) | Qullamaggie says 10%+ |
| ADV Dollar Volume | >= $1M median 20-day | Apollo liquidity gate |
| ATR% (14-day) | <= 15% | Apollo volatility cap |
| Market Cap | >= $500M | Apollo institutional floor |
| ATR stop width | <= 1.5× ATR-14 | Qullamaggie: "1x, max 1.5x ATR" |
| EP cooldown | 60 days same ticker | Qullamaggie: "failure rate higher on repeats" |
| Prior momentum | Not yet implemented | Qullamaggie: "not rallied past 3-6 months" |

---

## Part D — Exit Reasons & Skip Reasons

### Exit reasons

| Reason | Trigger | Price |
|--------|---------|-------|
| `stop_hit` | Bar low <= stop (ORB low Day 1, hard_stop Day 2+) | Stop price |
| `partial_profit` | Day 3-5 partial take (Apollo rule B5) | Bar close |
| `sma_trail_stop` | Daily close < effective stop | Bar close |
| `data_ended` | Ran out of price data | Last close |

### Skip reasons

| Reason | Trigger |
|--------|---------|
| `orb_no_breakout` | Price never exceeded ORB High on Day 1 |
| `stop_too_wide` | Entry-to-stop distance > 1.5× ATR-14 |
| `adv_too_low` | Dollar volume < $1M |
| `adv_no_data` | No volume data available |
| `atr_too_high` | ATR% > 15% |
| `mcap_too_low` | Market cap < $500M |
| `data_unavailable` | No intraday bars for Day 1 |
| `no_valid_entry` | Day 1 simulation returned nothing |

---

## Part E — Risk Safeguards (Apollo)

- Max concurrent positions: 5
- Max daily new trades: 3
- Max sector concentration: 40%
- Max portfolio heat: 20% of account
- Position size: Fixed $10K per trade (Phase 3: risk-based sizing)

---

## Part F — Implementation

Files: `agents/market_intelligence/backtester/`

| File | Purpose |
|------|---------|
| `filters.py` | Pre-trade filters + `compute_atr_14()` |
| `engine.py` | Day 1 ORB sim + Day 2+ SMA trail sim |
| `models.py` | `BacktestTrade` with `orb_high`, `orb_low`, `atr_14`, `breakeven_stop` |
| `report.py` | Text report + CSV export |
| `tracker.py` | Live paper trade tracker (daily updates) |
| `intraday.py` | Polygon 5-min bar fetcher |
| `safeguards.py` | Position/risk limits |

---

## Version History

| Date | Change |
|------|--------|
| 2026-03-28 | v2.1: Verify rules against source, separate Qullamaggie vs Apollo additions, fix re-entry stop |
| 2026-03-27 | v2: ORB entry, ATR stop validation, 10/20 SMA trail, delayed partial profit |
| 2026-03-19 | v1: Buy at open, day-low ratchet trail, EOD Day 1 partial |
