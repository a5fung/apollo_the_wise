---
name: claude-md-changelog
description: Use when adding, compressing or graduating a "Changes Made — Recent" entry in CLAUDE.md, or when CLAUDE.md nears its 40k-char ceiling.
---

# Maintaining CLAUDE.md's "Changes Made — Recent"

Keep new entries in **Recent** above. After ~2 weeks compress each to ONE bullet (`topic — key change & lesson`) and **graduate it into `CHANGELOG.md`** (don't keep the compressed form here). Drop "Files Changed" (git has it), "Post-deploy verification" once verified, cleanup SQL once applied. **⚠ Always leave ≥1 dated `### YYYY-MM-DD` entry** — `system_audit._recent_changes_context` + `test_system_audit_recent_changes` require it; emptying Recent reds CI (6/19). Docs-only pushes skip the pre-push gate, so run that test before graduating.

Older history: see `CHANGELOG.md` (compressed log, on-demand only — not auto-loaded). For genuinely architectural decisions where the *why* outlives the code, optionally write a short `docs/decisions/NNNN-topic.md` ADR.

Target CLAUDE.md size: under 30k chars. Hard ceiling: 40k (warning threshold).
