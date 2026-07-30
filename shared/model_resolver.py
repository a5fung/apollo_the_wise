"""Model auto-resolution — newest concrete Claude id per tier, with fail-safe pins.

Operator ruling (2026-07-30, verbatim intent): "go with the leaders, but have
guardrails to make sure there's no major degradation … and we can always trace
back to when they were updated." So tiers TRACK the newest release
automatically; safety comes from guardrails + traceability, not frozen pins.

There is NO `-latest` alias in the API — `models.list` returns concrete ids
(claude-opus-5, claude-opus-4-8, claude-haiku-4-5-20251001, …), so "latest"
means resolving that list. This module is the ONE implementation of that
resolution, used by three consumers that must agree byte-for-byte:

  1. shared/llm_models.py            — binds tier constants at import (cache read only)
  2. agents/.../model_resolution.py  — the nightly refresh job (writes the cache)
  3. scripts/preflight_judge_eval_gate.py + preflight_model_resolution.py

DESIGN CONTRACT — read before touching:
  * PURE STDLIB, no app imports (llm_models imports THIS, never the reverse;
    the host-side deploy gates import it too). No network in the resolve path.
  * Resolution is CACHE-FILE based: the nightly refresh job calls models.list
    and writes `logs/model_resolution.json` (bind-mounted in prod, so the
    market-agent writes it and the execution container + host deploy gates read
    it). Import-time resolution ONLY reads that file — zero API calls per LLM
    invocation, zero at import.
  * FAIL SAFE, always: any failure (missing/corrupt cache, unparseable id,
    family mismatch, resolver bug) returns the committed PIN. A resolver
    exception must never take the trading system down — resolve_tier cannot
    raise.
  * NEVER BELOW THE PIN: a cache id older than the committed pin is ignored
    (protects against a stale/corrupt cache downgrading a tier).
  * An OVERRIDE (shared/llm_models.py `_TIER_OVERRIDES`) beats everything —
    that is the one-edit rollback path.

Version ordering ("how do we know opus-5 is newer than opus-4-8"):
  ids parse as  claude-{family}-{version…}[-YYYYMMDD]  or the legacy
  claude-{version…}-{family}-YYYYMMDD shape. The numeric tokens form a version
  tuple compared lexicographically — (5,) > (4, 8) > (4, 5) — with the snapshot
  date as tie-break ((4, 5, 20251101) > (4, 5, 20251001)). An id with any token
  that is neither a known family word nor pure digits (claude-fable-5's
  "fable", claude-mythos-preview's "preview", claude-2.1's "2.1") does NOT
  parse and is EXCLUDED from candidacy — we never resolve onto an id we cannot
  order, and never across families/tiers.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# The tiers we resolve. Families outside this set (fable, mythos, …) are never
# candidates — the trading system's role bindings only use these three.
TIERS: tuple[str, ...] = ("opus", "sonnet", "haiku")

CACHE_SCHEMA = 1
_CACHE_ENV = "APOLLO_MODEL_RESOLUTION_CACHE"
_PREFIX = "claude-"
_SNAPSHOT_RE = re.compile(r"^(19|2\d)\d{6}$")  # YYYYMMDD


def default_cache_path() -> Path:
    """`<repo_root>/logs/model_resolution.json` (env-overridable).

    In prod containers this is /app/logs/… — bind-mounted to the host repo's
    logs/ dir, so the market-agent's nightly refresh is visible to the
    execution container at its next boot AND to the host-side deploy gates.
    (The orchestrator container does not mount logs/ — it runs on the pins,
    which is the documented fail-safe, not an error.)
    """
    env = os.environ.get(_CACHE_ENV)
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "logs" / "model_resolution.json"


# ── Parsing / ordering ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class ParsedId:
    id: str
    family: str
    version: tuple[int, ...]
    snapshot: int  # YYYYMMDD, or 0 when the id carries no date suffix

    @property
    def sort_key(self) -> tuple:
        # version tuple compares lexicographically: (5,) > (4, 8) > (4, 5).
        # snapshot breaks ties between dated releases of the same version;
        # the id string is a last-resort deterministic tie-break.
        return (self.version, self.snapshot, self.id)


def parse_model_id(model_id: str) -> ParsedId | None:
    """Parse a concrete Claude id into (family, version, snapshot); None if the
    shape is unrecognised (unknown family word, non-numeric token, no version).
    Unparseable ids are simply not candidates — that is the fail-safe."""
    if not isinstance(model_id, str) or not model_id.startswith(_PREFIX):
        return None
    tokens = model_id[len(_PREFIX):].split("-")
    if not tokens or any(t == "" for t in tokens):
        return None
    snapshot = 0
    if len(tokens) >= 2 and _SNAPSHOT_RE.match(tokens[-1]):
        snapshot = int(tokens[-1])
        tokens = tokens[:-1]
    family: str | None = None
    version: list[int] = []
    for tok in tokens:
        if tok in TIERS:
            if family is not None:
                return None  # two family words — not a shape we know
            family = tok
        elif tok.isdigit():
            version.append(int(tok))
        else:
            return None  # "fable", "preview", "2.1", "latest", … — cannot order
    if family is None or not version:
        return None
    return ParsedId(id=model_id, family=family, version=tuple(version), snapshot=snapshot)


def newest_per_tier(model_ids: list[str]) -> dict[str, str]:
    """Newest parseable id per tier from an API `models.list` id list.
    Tiers with no parseable candidate are simply absent from the result."""
    best: dict[str, ParsedId] = {}
    for mid in model_ids:
        parsed = parse_model_id(mid)
        if parsed is None:
            continue
        cur = best.get(parsed.family)
        if cur is None or parsed.sort_key > cur.sort_key:
            best[parsed.family] = parsed
    return {tier: p.id for tier, p in best.items()}


def is_newer(candidate: str, than: str) -> bool:
    """True iff both ids parse, share a family, and candidate orders strictly
    newer. Unparseable input → False (fail-safe: never claim newness)."""
    a, b = parse_model_id(candidate), parse_model_id(than)
    if a is None or b is None or a.family != b.family:
        return False
    return a.sort_key > b.sort_key


# ── Cache file ───────────────────────────────────────────────────────────────

def read_cache(cache_path: Path | None = None) -> dict | None:
    """Parsed cache dict, or None when missing/corrupt (corrupt is logged)."""
    path = cache_path or default_cache_path()
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("resolved"), dict):
            logger.warning("model_resolver: cache %s has no 'resolved' map — ignoring", path)
            return None
        return data
    except Exception as e:  # any read/parse failure → behave as "no cache"
        logger.warning("model_resolver: unreadable cache %s (%s) — falling back to pins", path, e)
        return None


def write_cache(resolved: dict[str, str], changed_at: dict[str, str],
                candidates: dict[str, list[str]] | None = None,
                cache_path: Path | None = None) -> Path:
    """Atomically write the resolution cache (tmp file + os.replace)."""
    path = cache_path or default_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": CACHE_SCHEMA,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "source": "models.list",
        "resolved": dict(resolved),
        "changed_at": dict(changed_at),
        "candidates": dict(candidates or {}),
    }
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


# ── Resolution ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TierResolution:
    tier: str
    model: str
    source: str            # "override" | "cache" | "pin"
    changed_at: str | None  # ISO ts when the cache last CHANGED this tier (cache source only)
    note: str = ""          # why a fallback happened, for forensics


def resolve_tier(tier: str, pin: str, override: str | None = None,
                 cache_path: Path | None = None) -> TierResolution:
    """The one resolve function. Precedence: override > cache (never below the
    pin) > pin. CANNOT RAISE — any internal failure returns the pin."""
    try:
        return _resolve_tier_inner(tier, pin, override, cache_path)
    except Exception as e:  # belt-and-braces: a resolver bug must not stop boot
        logger.warning("model_resolver: resolve_tier(%s) failed (%s) — using pin %s",
                       tier, e, pin)
        return TierResolution(tier, pin, "pin", None, f"resolver error: {e}")


def _resolve_tier_inner(tier: str, pin: str, override: str | None,
                        cache_path: Path | None) -> TierResolution:
    if override:
        if isinstance(override, str) and override.startswith(_PREFIX):
            return TierResolution(tier, override, "override", None,
                                  "explicit tier override (rollback/pin lever)")
        logger.warning("model_resolver: malformed %s override %r ignored — using pin %s",
                       tier, override, pin)
        return TierResolution(tier, pin, "pin", None, f"malformed override {override!r}")

    cache = read_cache(cache_path)
    if cache is None:
        return TierResolution(tier, pin, "pin", None, "no resolution cache")

    cached = cache.get("resolved", {}).get(tier)
    if not isinstance(cached, str) or not cached:
        return TierResolution(tier, pin, "pin", None, "tier absent from cache")

    parsed = parse_model_id(cached)
    if parsed is None or parsed.family != tier:
        logger.warning("model_resolver: cached %s id %r unparseable/wrong-family — using pin %s",
                       tier, cached, pin)
        return TierResolution(tier, pin, "pin", None, f"cached id {cached!r} rejected")

    if cached == pin:
        return TierResolution(tier, pin, "pin", None, "cache agrees with pin")

    if not is_newer(cached, pin):
        # never resolve BELOW the committed pin (stale cache / manual pin bump)
        logger.warning("model_resolver: cached %s id %s is not newer than pin %s — using pin",
                       tier, cached, pin)
        return TierResolution(tier, pin, "pin", None,
                              f"cache {cached} not newer than pin")

    changed_at = cache.get("changed_at", {}).get(tier)
    if not isinstance(changed_at, str):
        changed_at = None
    return TierResolution(tier, cached, "cache", changed_at)
