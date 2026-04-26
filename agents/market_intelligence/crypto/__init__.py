"""Crypto RS surveillance module — shadow-mode by default.

See /CRYPTO_RS_DESIGN.md for the full design spec.

Shadow flag: agents.market_intelligence.constants.CRYPTO_RS_ENABLED
- false (default): nightly ingest runs, RS computed, audit-only on trigger fire,
  Telegram surfaces return shadow-mode message.
- true: full alt-season trigger Telegram alerts + /crypto + /altseason briefings.
"""
