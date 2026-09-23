"""#509 model auto-resolution — shared/model_resolver.py (the pure-stdlib resolver).

Pins:
  1. parse_model_id: version/snapshot parsing, family recognition, and the
     "cannot order it -> not a candidate" fail-safe for fable/preview/legacy
     shapes (claude-fable-5, claude-mythos-preview, claude-2.1, two family
     words, no version at all).
  2. newest_per_tier: picks the highest sort_key per family, ignores
     unparseable ids, from the EXACT live models.list shape the operator
     verified (#509 card): opus-5/sonnet-5/fable-5/opus-4-8/opus-4-7/
     sonnet-4-6/opus-4-6/opus-4-5-20251101/haiku-4-5-20251001.
  3. is_newer: strict-newer, same-family-only, fail-safe False on any
     unparseable input.
  4. read_cache/write_cache: atomic roundtrip; missing file, corrupt JSON, and
     a schema missing 'resolved' all degrade to None (never raise).
  5. resolve_tier precedence + fail-safe: override > cache (never below pin) >
     pin; malformed override, absent/corrupt cache, unparseable/wrong-family
     cached id, and a cache id NOT newer than the pin all fall back to the
     pin; an internal resolver exception is swallowed and returns the pin —
     resolve_tier CANNOT raise.
"""
from pathlib import Path
from unittest.mock import patch

from shared import model_resolver as mr

# The exact live `models.list` ids the operator verified for #509 (card text),
# newest-first as the API actually returns them.
LIVE_IDS = [
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-opus-4-5-20251101",
    "claude-haiku-4-5-20251001",
]


# ─── parse_model_id ─────────────────────────────────────────────────────────

def test_parse_simple_version():
    p = mr.parse_model_id("claude-opus-5")
    assert p.family == "opus" and p.version == (5,) and p.snapshot == 0


def test_parse_dotted_version():
    p = mr.parse_model_id("claude-opus-4-8")
    assert p.family == "opus" and p.version == (4, 8) and p.snapshot == 0


def test_parse_snapshot_dated():
    p = mr.parse_model_id("claude-haiku-4-5-20251001")
    assert p.family == "haiku" and p.version == (4, 5) and p.snapshot == 20251001


def test_parse_rejects_unknown_family_word():
    # "fable" is not in TIERS — cannot order it, never a candidate.
    assert mr.parse_model_id("claude-fable-5") is None


def test_parse_rejects_preview_token():
    assert mr.parse_model_id("claude-mythos-preview") is None


def test_parse_rejects_non_integer_dotted_version():
    assert mr.parse_model_id("claude-2.1") is None


def test_parse_rejects_two_family_words():
    assert mr.parse_model_id("claude-opus-sonnet-5") is None


def test_parse_rejects_no_version_at_all():
    assert mr.parse_model_id("claude-opus") is None


def test_parse_rejects_non_claude_prefix():
    assert mr.parse_model_id("gpt-5") is None


def test_parse_rejects_non_string():
    assert mr.parse_model_id(None) is None
    assert mr.parse_model_id(123) is None


# ─── newest_per_tier ────────────────────────────────────────────────────────

def test_newest_per_tier_live_shape():
    result = mr.newest_per_tier(LIVE_IDS)
    assert result == {
        "opus": "claude-opus-5",
        "sonnet": "claude-sonnet-5",
        "haiku": "claude-haiku-4-5-20251001",
    }
    # fable is genuinely excluded, not silently mapped somewhere
    assert "fable" not in result


def test_newest_per_tier_snapshot_tiebreak():
    ids = ["claude-opus-4-5-20251001", "claude-opus-4-5-20251101"]
    assert mr.newest_per_tier(ids) == {"opus": "claude-opus-4-5-20251101"}


def test_newest_per_tier_empty_or_all_unparseable():
    assert mr.newest_per_tier([]) == {}
    assert mr.newest_per_tier(["claude-fable-5", "gpt-5", "claude-2.1"]) == {}


# ─── is_newer ───────────────────────────────────────────────────────────────

def test_is_newer_true():
    assert mr.is_newer("claude-opus-5", "claude-opus-4-8") is True


def test_is_newer_false_when_older_or_equal():
    assert mr.is_newer("claude-opus-4-6", "claude-opus-4-8") is False
    assert mr.is_newer("claude-opus-4-8", "claude-opus-4-8") is False


def test_is_newer_false_cross_family():
    assert mr.is_newer("claude-sonnet-5", "claude-opus-4-8") is False


def test_is_newer_false_unparseable():
    assert mr.is_newer("claude-fable-5", "claude-opus-4-8") is False
    assert mr.is_newer("claude-opus-4-8", "not-a-model") is False


# ─── cache file ─────────────────────────────────────────────────────────────

def test_cache_roundtrip(tmp_path: Path):
    path = tmp_path / "model_resolution.json"
    written = mr.write_cache(
        {"opus": "claude-opus-5"}, {"opus": "2026-07-30T00:00:00+00:00"},
        candidates={"opus": ["claude-opus-5", "claude-opus-4-8"]},
        cache_path=path,
    )
    assert written == path
    data = mr.read_cache(path)
    assert data["resolved"] == {"opus": "claude-opus-5"}
    assert data["schema"] == mr.CACHE_SCHEMA


def test_cache_missing_file_returns_none(tmp_path: Path):
    assert mr.read_cache(tmp_path / "nope.json") is None


def test_cache_corrupt_json_returns_none(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert mr.read_cache(path) is None


def test_cache_missing_resolved_key_returns_none(tmp_path: Path):
    path = tmp_path / "bad2.json"
    path.write_text('{"schema": 1}', encoding="utf-8")
    assert mr.read_cache(path) is None


# ─── resolve_tier ───────────────────────────────────────────────────────────

def test_resolve_no_cache_returns_pin(tmp_path: Path):
    res = mr.resolve_tier("opus", "claude-opus-4-8", cache_path=tmp_path / "none.json")
    assert res.model == "claude-opus-4-8"
    assert res.source == "pin"


def test_resolve_override_wins(tmp_path: Path):
    res = mr.resolve_tier("opus", "claude-opus-4-8", override="claude-opus-4-7",
                          cache_path=tmp_path / "none.json")
    assert res.model == "claude-opus-4-7"
    assert res.source == "override"


def test_resolve_malformed_override_falls_back_to_pin(tmp_path: Path):
    res = mr.resolve_tier("opus", "claude-opus-4-8", override="not-a-model",
                          cache_path=tmp_path / "none.json")
    assert res.model == "claude-opus-4-8"
    assert res.source == "pin"


def test_resolve_cache_newer_than_pin_wins(tmp_path: Path):
    path = tmp_path / "cache.json"
    mr.write_cache({"opus": "claude-opus-5"}, {"opus": "2026-07-30T00:00:00+00:00"},
                   cache_path=path)
    res = mr.resolve_tier("opus", "claude-opus-4-8", cache_path=path)
    assert res.model == "claude-opus-5"
    assert res.source == "cache"
    assert res.changed_at == "2026-07-30T00:00:00+00:00"


def test_resolve_cache_equal_to_pin_reports_pin(tmp_path: Path):
    path = tmp_path / "cache.json"
    mr.write_cache({"opus": "claude-opus-4-8"}, {}, cache_path=path)
    res = mr.resolve_tier("opus", "claude-opus-4-8", cache_path=path)
    assert res.model == "claude-opus-4-8"
    assert res.source == "pin"


def test_resolve_never_below_pin(tmp_path: Path):
    # A stale/corrupt cache holding an OLDER id than the committed pin must
    # never downgrade the running system.
    path = tmp_path / "cache.json"
    mr.write_cache({"opus": "claude-opus-4-6"}, {}, cache_path=path)
    res = mr.resolve_tier("opus", "claude-opus-4-8", cache_path=path)
    assert res.model == "claude-opus-4-8"
    assert res.source == "pin"
    assert "not newer than pin" in res.note


def test_resolve_cached_id_wrong_family_falls_back(tmp_path: Path):
    path = tmp_path / "cache.json"
    mr.write_cache({"opus": "claude-sonnet-5"}, {}, cache_path=path)
    res = mr.resolve_tier("opus", "claude-opus-4-8", cache_path=path)
    assert res.model == "claude-opus-4-8"
    assert res.source == "pin"


def test_resolve_cached_id_unparseable_falls_back(tmp_path: Path):
    path = tmp_path / "cache.json"
    mr.write_cache({"opus": "claude-fable-5"}, {}, cache_path=path)
    res = mr.resolve_tier("opus", "claude-opus-4-8", cache_path=path)
    assert res.model == "claude-opus-4-8"
    assert res.source == "pin"


def test_resolve_tier_absent_from_cache_falls_back(tmp_path: Path):
    path = tmp_path / "cache.json"
    mr.write_cache({"sonnet": "claude-sonnet-5"}, {}, cache_path=path)
    res = mr.resolve_tier("opus", "claude-opus-4-8", cache_path=path)
    assert res.model == "claude-opus-4-8"
    assert res.source == "pin"


def test_resolve_tier_cannot_raise_even_on_internal_bug(tmp_path: Path):
    with patch.object(mr, "_resolve_tier_inner", side_effect=RuntimeError("boom")):
        res = mr.resolve_tier("opus", "claude-opus-4-8", cache_path=tmp_path / "x.json")
    assert res.model == "claude-opus-4-8"
    assert res.source == "pin"
    assert "resolver error" in res.note
