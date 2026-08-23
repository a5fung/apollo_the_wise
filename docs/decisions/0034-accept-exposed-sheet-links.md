# ADR 0034 — Accept the exposed Google Sheet links (operator ruling)

**Date:** 2026-08-22 · **Status:** Accepted · **Decider:** operator

## Context

`.streamlit/secrets.toml` was committed to the PUBLIC repo `github.com/a5fung/portfolio-app2`
on 2026-02-07 and stayed tracked until 2026-06-04. Untracking does not remove it from history,
so the values are still recoverable by anyone who cloned or browses the history.

Exposed (verified by reading every historical version, names only): `app_password` and four
Google Sheet URLs — `public_sheet_url`, `longterm_sheet_url`, `transactions_sheet_url`,
`trading_journal_url`. Those are link-readable CSV exports, so holding one reads the portfolio
data without touching the dashboard. **No Anthropic key was ever in the file** (the repo's own
CLAUDE.md claim to the contrary is wrong — zero `sk-ant-` matches across all versions).

`app_password` **was rotated 2026-08-10** and is not part of this decision.

## Decision

**The four Sheet links are NOT rotated. The residual exposure is accepted.**

Operator, 2026-08-22: *"this is not happening, i have those sheets for years, i am not changing
it."*

## Why rotation was the only fix, and why it was rejected

Rotation is not possible in place. Google reuses a document's publish token forever —
un-publishing revokes access, re-publishing restores the **same** URL. Restricting the
document's link-sharing does break the old URLs, but it equally breaks every other export link
on that document, because all four tabs live in ONE spreadsheet. The only true rotation is a NEW
document (new ID → new links), then deleting the original.

That means recreating spreadsheets the operator has maintained for years and rewiring everything
that reads them. He judged the cost above the risk. That is his data and his call.

## Consequence, stated plainly

Anyone who obtained a link from the public history between 2026-02-07 and 2026-06-04 can still
read the portfolio, long-term tracker, transactions and trading journal, indefinitely. This is a
read-only data exposure: no write access, no credentials, no trading access.

## What was done instead

- Password rotated (2026-08-10).
- ⚠ **Do not re-open this as a task.** It was raised, priced, and ruled. Re-surfacing it wastes
  his time — the 2026-08-22 session lost an hour to an attempted rotation that broke the live
  dashboard and had to be undone.
- The stale Anthropic-key claim in `portfolio-app2`'s CLAUDE.md should still be corrected when
  that repo is next touched — it is wrong and would mislead a future reader into a false panic.
