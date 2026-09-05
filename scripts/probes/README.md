# scripts/probes/ — throwaway diagnostic probes

One-off, read-only diagnostic / reconstruction scripts written to investigate a
specific incident or question, then kept as the reproduction artifact. They are
NOT part of any pipeline (deploy.sh, CI, cron, the data_gated_reviews registry)
and NOT imported by any module — that's the criterion for living here (#261).

If a probe graduates into a re-runnable tool (cited by a data_gated_review, a
scheduled job, or imported as a shared helper), move it back up to `scripts/`.
Shared helper modules (`_judge_replay_common`, `_grounded_reconstruct`,
`_backward_check_utils`, `_judge_review_sql`) and the coupled `_270_*` replay
cluster deliberately stay in `scripts/` — they are imported by real code/tests.

## Reading a psql capture

Several probes read a `.psv`/`.tsv` file captured straight from `psql` output
(`\pset format unaligned`, `|`-delimited). That output carries a header row
and a `(N rows)` footer line — a footer parsed as data (e.g. as a ticker) is a
real defect, not a hypothetical: #623's `_623_fetch_shares_out.py` did exactly
this on 2026-09-04, feeding literal `(3458 rows)` to Polygon as a ticker and
tripping a live `api_failure_polygon` alert. Skip both: filter any row/line
whose first field starts with `"("` (see `_623_join.py::load_psv`,
`_623_replay.py::load_population`/`load_minutes_from_psv`) — copy that pattern
rather than inventing a variant.

## Calling a live collector/broker helper (`agents.market_intelligence.collector`,
`broker/alpaca_client.py`, etc.)

A probe that imports these calls the SAME helpers, in the SAME process, with
the SAME real API key the live app uses — nothing downstream can otherwise
tell a probe's failure from a live one. Set `APOLLO_CALL_ORIGIN=probe` in the
probe's own process **before** importing the helper:

```python
import os
os.environ.setdefault("APOLLO_CALL_ORIGIN", "probe")
from agents.market_intelligence.collector import get_ticker_details  # noqa: E402
```

`llm_health.alert_api_failure` still writes the `api_failure_<provider>` audit
row (marked `origin=probe`, queryable via `show errors`) but never pages and
never counts toward a live sustained-failure escalation — see
`agents/market_intelligence/llm_health.py`'s PROBE-ORIGIN section. Never set
this in any live-path module.
