# Theme assignment — what it actually costs at steady state, and against what

**2026-09-19.** Operator, 2026-08-10: *"let's monitor and find out the steady state cost."* The
line's own condition was **pull it if the backlog does not clear**. Nine weekday runs, read from
`api_usage` (`caller = 'theme_assignment'`, exactly — **not** `ILIKE '%assign%'`, which also
catches `theme_ecosystem_assignment` and inflates every figure) joined to
`assignment_llm_proposed.candidate_pool_size`.


## Method and population — which rows, over what window, and how the set was derived

**Window:** the nine ET weekday nights 2026-09-08 → 2026-09-18 inclusive. Weekends are excluded
because the theme jobs are `day_of_week="mon-fri"` and `mi_themes` carries zero weekend rows.

**Cost rows:** `api_usage` filtered to **`caller = 'theme_assignment'` exactly**, grouped by
`date(created_at AT TIME ZONE 'America/New_York')`.

⚠ **THE POPULATION TRAP, and I walked into it first.** My initial read used
`caller ILIKE '%assign%'`, which ALSO matches **`theme_ecosystem_assignment`** — a different job
with its own budget. That inflated every night by roughly 20% (e.g. 09-08 reads $0.2529 under the
ILIKE against the true $0.2221). The figures in this document are the exact-match set. Anyone
re-running this must use the equality, not the pattern.

**Pool rows:** `mi_audit_log` where `event_type = 'assignment_llm_proposed'`, taking
`detail::jsonb->>'candidate_pool_size'` and `->>'batch_size'` per night. The pool is the
*candidate* set the assignment step was handed, which is the denominator the DoD demands — not
the number of proposals it returned, and not the birth funnel's `uncovered=` count, which belongs
to theme DISCOVERY and is a different quantity entirely.

**Join:** the two are joined on the ET date, so each row pairs a night's spend with the pool that
night's spend was spent on.

## The pair — cost is meaningless without the pool it acts on

| ET night | candidate pool | batch | calls | cost | at max_tokens | $/candidate |
|---|---|---|---|---|---|---|
| 2026-09-08 | 178 | 18 | 10 | $0.2221 | 0 | 0.00125 |
| 2026-09-09 | 182 | 18 | 11 | $0.2433 | 0 | 0.00134 |
| 2026-09-10 | 172 | 18 | 10 | $0.2084 | 0 | 0.00121 |
| 2026-09-11 | 164 | 18 | 10 | $0.2152 | 0 | 0.00131 |
| 2026-09-14 | 179 | 18 | 10 | $0.2250 | 0 | 0.00126 |
| 2026-09-15 | 169 | 18 | 10 | $0.2142 | 0 | 0.00127 |
| 2026-09-16 | 165 | 18 | 10 | $0.2181 | 0 | 0.00132 |
| 2026-09-17 | 158 | 18 | 9 | $0.2175 | 0 | 0.00138 |
| 2026-09-18 | 159 | 18 | 9 | $0.2199 | 0 | 0.00138 |

## What the numbers say

- **Cost is FLAT: $0.208–$0.243 a night, mean $0.2204.** No drift across nine sessions.
- **Implied run-rate ≈ $4.63/month** (21 weekdays). In plain terms: assigning tickers to themes
  costs about five dollars a month.
- **The backlog IS clearing — gently. The pool fell 178 → 159**, roughly −2 candidates a session.
  That is the condition the task set for keeping it.
- **`batch = 18` HELD, and this is the first time it has been MEASURED rather than modelled.** The
  task flagged it as modelled precisely because every pre-fix call was censored at the token cap,
  so no clean sample existed. It reads 18 on all nine nights.
- **Zero calls hit `max_tokens` on any night.** The 2026-08-10 output-bounding fix held.
- **$/candidate rises slightly, 0.00125 → 0.00138.** That is the expected shape of a shrinking
  pool, not a regression: fixed per-call overhead is amortised over fewer stocks.

## Recommendation — KEEP. Do not bound the pool, do not pull it.

Nothing here justifies an intervention. The cost is ~$5/month, it is not growing, no call is
hitting the ceiling, and the pool the task was worried about is going DOWN rather than up.
Bounding a pool that is already shrinking would trade real coverage for no saving.

⚠ **Stated so it is not over-read: n = 9 sessions, and the decline is gentle.** At −2 a session the
pool would take ~80 sessions to empty, and it may well plateau in the 120–160 band instead of
emptying. **That is not a reason to pull a $5/month job** — it is a reason not to claim the
backlog is solved. If the pool ever turns and climbs past ~250 while cost tracks it, re-read this;
the instrument is one SQL join and takes a minute.

## What this does not answer

- **Whether the assignments are any GOOD.** This measures cost and pool size. Nothing here says a
  ticker was assigned to the right theme; that is #368/#655 territory and needs his labels.
- **Whether the pool will keep falling.** n = 9 sessions with a −2/session slope and ordinary
  day-to-day noise of ±10. The direction is real enough to satisfy *"does the backlog clear"*; the
  slope is not strong enough to forecast an empty pool, and a plateau in the 120–160 band is fully
  consistent with this data.
- **Why the pool is falling.** Fewer new high-RS names, better coverage by existing themes, and a
  narrowing candidate rule would all look identical here.
- **The cost of everything else the theme engine does.** `theme_discovery` ($4.18 over the
  window), `theme_validation`, `theme_ecosystem_assignment`, `theme_merge_adjudication` and
  `perplexity_news_search` ($5.29, the single largest) are all out of scope — this line was about
  ASSIGNMENT. The engine's total bill is a different question and a bigger number.
- **Whether `batch = 18` is the RIGHT size.** It held, which is what was asked. Whether 18 is
  optimal against truncation risk and per-call overhead is the 2026-08-18 analysis's subject, not
  this one.
