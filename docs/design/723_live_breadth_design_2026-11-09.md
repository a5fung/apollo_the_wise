# #723 — live market breadth (the Today view) — design (2026-11-09, step 1)

His ask (2026-11-08): *"market breath should be live"* · *"Only today needs to be live"*. Only the TODAY numbers refresh
during the session: new highs / new lows, advances / declines, the 19 groups' and the themes' 1-day returns. 1W / 1M /
YTD and the stages stay on the last close.

## Measured (read-only probe in apollo-market, Mon 11-09 ~13:20 ET — `scripts/probes/_723_design_1109/probe_sources.out`)

| Source | Coverage | Time per refresh | Freshness | Cost |
|---|---|---|---|---|
| Polygon whole-market snapshot (`collector.get_snapshot_all`) | 13,257 tickers, 11,552 with today's high, one call | 5.3 s | **15-17 min late** (median last-trade age 17.1 min) | $0 (current plan) |
| Alpaca SIP snapshots (`collector.get_alpaca_snapshots_batch`, 100 per call) | 958 of 1,000 sampled | 1.6 s per 1,000 → **~8 s for the ~5,000 universe** (~50 calls) | **real time** | $0 (SIP already paid) |

## Decisions (mine — none is THE LINE)

1. **Price source: Alpaca SIP snapshots** (real time). The universe = the nightly export's CS + ADRC ≥ $1 names (~5,000).
   A name Alpaca does not return is counted as missing and reported, never guessed.
2. **Cadence:** every 15 min, 09:45 → 16:00 ET, Mon-Fri trading days (~26 refreshes, ~1,300 calls a day).
3. **What is computed live** (from each snapshot's daily bar + the nightly reference):
   - new high = today's high ≥ the prior-252-session high (from the reference); new low likewise; eligibility as the nightly rule;
   - advance / decline = latest price vs the previous close;
   - groups' and themes' 1-day return = equal-weight over today's members (the nightly membership), the same "counted once" rule.
4. **Nightly reference file** (step 2, written by the 18:30 ET export): per ticker — previous close, prior-252 high / low,
   eligibility, group and theme indexes. The intraday job only compares; no history is re-read during the day.
5. **Delivery to the page:** NOT the main branch (a push there makes Streamlit Cloud reload — the ~15 min lag he has
   seen). Apollo force-pushes ONE small file (`apollo_breadth_live.json`) to a dedicated branch `live-breadth` of
   portfolio-app2 on each refresh (one commit kept, no history growth); the page reads it through the GitHub contents
   API with a **read-only token** in Streamlit secrets, cached ~60 s.
6. **Staleness:** the file carries `as_of` (ET). The page shows "Live · as of 11:45 ET" when it is ≤ 20 min old on a
   trading day, otherwise the last-close numbers labelled "Last close". A failed refresh never leaves an old number
   shown as live.
7. **Deploy scope:** market-agent (the job runs in the market agent; collector is already there). No execution change.

## One action from him (step 4 depends on it)

Create a fine-grained GitHub token with **read-only Contents access to `portfolio-app2` only**, and add it to the
Streamlit app's secrets as `GITHUB_READ_TOKEN`. (I cannot do this: his GitHub and Streamlit accounts.)

## Steps

| # | What | When |
|---|---|---|
| 2 | nightly reference in the export (+ tests) | Tue 11-10 |
| 3 | intraday job (+ tests, the stale/missing paths) | Tue-Wed |
| — | deploy market-agent | Wed 11-11 21:15 ET, his go |
| 4 | page: the Today view reads the live file (token), falls back to the last close | Thu 11-12, his push |
| 5 | in-session check: one refresh vs an independent count at the same minute | Fri 11-13 |
