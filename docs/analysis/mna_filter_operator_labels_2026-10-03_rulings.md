# #692 — his rulings on the pinned-price build (2026-10-03)

His word: *"Go with rec"* — to all four items put to him after the pin-layer build. n = 151 replayed stock-days (`scripts/probes/_692/replay_pin_2026-10-03.jsonl`).

## Population

Which rows: every `mna_filter_fired` / veto / acquirer-skip audit row from 2026-05-15 to 2026-10-02, collapsed to one row per ticker and day (151 stock-days, 137 of them blocked by the old filter), read-only from prod (`scripts/probes/_692/population_mna_events_2026-05-15_2026-10-02.jsonl`); prices from `mi_daily_closes` and the 09:30–10:30 ET minute bars of each day (`scripts/probes/_692/pin/`).

## The rulings

1. A news-nominated EP name is held out of the alert until the 09:35 open-window read, then released or blocked.
2. A buyout TARGET is graded on its own merits; the `mna` grade is reserved for a signed reverse-merger shell; the filter (news nominates, price decides) alone blocks targets.
3. A price-only EP arm: a gap of 20%+ whose 09:30–09:34 window trades within 0.5% blocks regardless of the news.
4. NUVL 2026-06-09 (GSK bid, pinned at 0.11%) is now blocked and IRDM 2026-06-29 (Rocket Lab deal, moved 3.3%) is now released — both accepted.

Also from him the same morning, on the accuracy review: *"It says one ran >20% but doesn't show it"* — the summary line now names the stock.

## What this does not answer

- Whether the 0.5% / 1.0% / 2.0% lines hold out of sample: they were chosen on this population (9 labelled nominated EP rows for the open window); the forward `mna_filter_released` stream and the monthly review measure them from here.
