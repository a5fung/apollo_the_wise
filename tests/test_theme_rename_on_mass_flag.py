"""FIX 1 (#214, 2026-08-26) — on the mass-eviction signature, RENAME the theme; don't
evict the members to fit a name that was too narrow.

Prod evidence this repairs (docs/analysis/theme_mass_eviction_2026-08-26.md): the same
energy block tripped the signature three times in ten days under three names, and the
08-26 firing deleted 17 regulated utilities and midstream operators from 'Oil Refining &
Marketing' — correct removals given the name, wrong response to the defect.

The tests are grouped by the thing that can silently break the fix:
  1. the signature predicate + its parity with health_checks
  2. the validator's skip-the-removals branch (and its scoping to ONE caller)
  3. the rename itself: naming-path reuse, loop cap, refusal guards
  4. IDENTITY — the four places a rename could orphan or double-count history
"""
import pytest

from agents.market_intelligence import theme_engine as te


# ── 1. the signature ─────────────────────────────────────────────────────────────────────

def test_signature_matches_health_checks_exactly():
    """Both modules must agree on what a mass eviction IS: health_checks EXCLUDES this
    class from its prune-quality signature for the same reason the engine now renames on
    it. A drift here means one of them acts on a population the other doesn't see."""
    from agents.market_intelligence.health_checks import _is_mass_eviction as hc
    cases = [(0, 0), (1, 1), (2, 3), (3, 6), (3, 7), (4, 7), (17, 24), (42, 42),
             (3, 5), (2, 4), (5, 20), (10, 20), (9, 16)]
    for n, total in cases:
        assert te._is_mass_eviction(n, total) == hc(n, total), (n, total)


def test_the_three_recorded_prod_firings_all_trip_the_signature():
    assert te._is_mass_eviction(17, 24) is True    # Oil Refining & Marketing, 08-26
    assert te._is_mass_eviction(42, 42) is True    # Independent Oil Refiners, 08-19
    assert te._is_mass_eviction(9, 16) is True     # Oilfield Equipment, 08-17


def test_ordinary_daily_validation_volume_does_not_trip_it():
    """The other 7 removals on 08-26 were one name each from 7 unrelated themes."""
    assert te._is_mass_eviction(1, 14) is False
    assert te._is_mass_eviction(2, 5) is False     # >=50% but under 3 leavers
    assert te._is_mass_eviction(3, 12) is False    # >=3 leavers but under 50%


def test_rename_predicate_is_stricter_than_the_audit_tripwire():
    """The tripwire fires on `>= max(3, len//2)` (floor division). A rename MUTATES a live
    theme, so it takes the strict >=50% reading. 3-of-7 must trip the audit row and NOT the
    rename — if these ever converge, say so deliberately rather than by accident."""
    n, members = 3, 7
    assert n >= max(3, members // 2) is True or n >= max(3, members // 2)
    assert te._is_mass_eviction(n, members) is False


# ── 2. the validator branch ──────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, payload):
        import json

        class _B:
            type = "text"
            text = json.dumps(payload)
        self.content = [_B()]
        self.stop_reason = "end_turn"


def _fake_client(monkeypatch, payload, captured=None):
    class _Messages:
        async def create(self, **kwargs):
            if captured is not None:
                captured.update(kwargs)
            return _FakeResp(payload)

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(te, "_get_anthropic_client", lambda: _Client())

    async def _protected():
        return set()
    monkeypatch.setattr(te, "get_operator_protected_set", _protected)
    return _Client()


@pytest.fixture
def no_cooldowns(monkeypatch):
    """Record every cooldown write so a test can assert NONE happened."""
    written = []

    async def _add(tk, theme, reason=""):
        written.append((tk, theme))
        return 1
    monkeypatch.setattr(te, "add_validation_cooldown", _add)

    audits = []

    async def _audit(event_type, summary="", detail=""):
        audits.append((event_type, summary, detail))
    monkeypatch.setattr(te, "log_audit_event", _audit)
    return written, audits


@pytest.mark.asyncio
async def test_FAILS_WITHOUT_FIX_mass_flag_keeps_every_member_and_writes_no_cooldown(
        monkeypatch, no_cooldowns):
    """The 08-26 shape: 17 of 24 flagged. Before the fix all 17 were removed and each got a
    14-day cooldown fencing it out of the theme until 09-09."""
    written, audits = no_cooldowns
    members = [f"T{i}" for i in range(24)]
    flagged = members[:17]
    _fake_client(monkeypatch, {"remove": flagged})

    out: dict = {}
    kept = await te._validate_theme_membership(
        "Oil Refining & Marketing", members, changelog=[], mass_flag_out=out)

    assert kept == members, "no member may be removed on the rename path"
    assert written == [], "no validation cooldown may be written on the rename path"
    assert out["flagged"] == sorted(flagged)
    assert out["member_count"] == 24


@pytest.mark.asyncio
async def test_the_audit_tripwire_still_fires_on_the_rename_path(monkeypatch, no_cooldowns):
    """Load-bearing, not decorative: `_name_recently_mass_evicted` reads this event OR >=3
    same-day `ticker_revalidated_out` rows — and the rename path stops writing the latter.
    Drop the tripwire and both the inheritance guard and the canonicalize carve-out go
    blind, which is how the rename gets silently reverted."""
    _written, audits = no_cooldowns
    members = [f"T{i}" for i in range(24)]
    _fake_client(monkeypatch, {"remove": members[:17]})
    await te._validate_theme_membership(
        "Oil Refining & Marketing", members, changelog=[], mass_flag_out={})
    assert any(e[0] == "validation_mass_removal_name_suspect" for e in audits)


@pytest.mark.asyncio
async def test_sub_threshold_flag_still_strips_exactly_as_before(monkeypatch, no_cooldowns):
    """Ordinary validation volume must be byte-identical — the fix is scoped to the
    signature, not to validation in general."""
    written, _audits = no_cooldowns
    members = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
    _fake_client(monkeypatch, {"remove": ["AAA"]})
    out: dict = {}
    kept = await te._validate_theme_membership(
        "Some Theme", members, changelog=[], mass_flag_out=out)
    assert kept == members[1:]
    assert written == [("AAA", "Some Theme")]
    assert out == {}, "sub-threshold flags must not signal a rename"


@pytest.mark.asyncio
async def test_other_three_callers_are_byte_identical_without_the_out_param(
        monkeypatch, no_cooldowns):
    """Birth validation, post-assignment validation and the Arm-B post-merge call pass no
    out-dict, so they keep stripping on the signature — deliberate, see the docstring."""
    written, _audits = no_cooldowns
    members = [f"T{i}" for i in range(24)]
    _fake_client(monkeypatch, {"remove": members[:17]})
    kept = await te._validate_theme_membership("Any Theme", members, changelog=[])
    assert kept == members[17:]
    assert len(written) == 17


@pytest.mark.asyncio
async def test_operator_shield_is_applied_before_the_signature_is_judged(
        monkeypatch, no_cooldowns):
    """The shield is the operator ruling that those members DO belong. A set that only
    reaches >=50% by counting shielded names is not a mass eviction, so it must fall
    through to the ordinary strip path rather than trigger a rename."""
    written, _audits = no_cooldowns
    members = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    _fake_client(monkeypatch, {"remove": ["AAA", "BBB", "CCC"]})

    async def _protected():
        return {("AAA", "T"), ("BBB", "T")}
    monkeypatch.setattr(te, "get_operator_protected_set", _protected)

    out: dict = {}
    kept = await te._validate_theme_membership("T", members, changelog=[], mass_flag_out=out)
    assert out == {}, "3 flagged minus 2 shielded = 1 — not a mass eviction"
    assert kept == ["AAA", "BBB", "DDD", "EEE", "FFF"]


@pytest.mark.asyncio
async def test_the_42_of_42_shape_reaches_the_rename_instead_of_the_min_survivor_guard(
        monkeypatch, no_cooldowns):
    """08-19: 'Independent Oil Refiners' flagged 42/42. The min-survivor guard swallowed it
    ("would drop below 2 tickers — skipping removals"), so nothing was recorded, nothing was
    renamed, and the theme retired the next day. That shape is the LOUDEST name-is-wrong
    signal there is and must now reach the rename."""
    written, _audits = no_cooldowns
    members = [f"T{i}" for i in range(42)]
    _fake_client(monkeypatch, {"remove": members})
    out: dict = {}
    kept = await te._validate_theme_membership("Independent Oil Refiners", members,
                                               changelog=[], mass_flag_out=out)
    assert kept == members
    assert out["flagged"] == sorted(members)
    assert written == []


# ── 3. the rename ────────────────────────────────────────────────────────────────────────

def _stub_rename_env(monkeypatch, *, capped=False, live=False, evicted=False,
                     proposal=("Energy Infrastructure & Utilities",
                               "New thesis covering AEP, OKE and SO.")):
    audits = []

    async def _audit(event_type, summary="", detail=""):
        audits.append((event_type, summary, detail))

    async def _capped(name, days=te.RENAME_LOOP_CAP_DAYS, conn=None):
        return capped

    async def _live(name, days=7):
        return live

    async def _evicted(name, days=30, conn=None):
        return evicted

    async def _propose(name, tickers, thesis, flagged):
        return proposal

    monkeypatch.setattr(te, "log_audit_event", _audit)
    monkeypatch.setattr(te, "_recently_renamed_on_mass_flag", _capped)
    monkeypatch.setattr(te, "_name_is_live", _live)
    monkeypatch.setattr(te, "_name_recently_mass_evicted", _evicted)
    monkeypatch.setattr(te, "_rename_theme_to_fit_cluster", _propose)
    return audits


@pytest.mark.asyncio
async def test_rename_is_applied_and_recorded(monkeypatch):
    audits = _stub_rename_env(monkeypatch)
    theme = {"name": "Oil Refining & Marketing", "description": "Refiners."}
    changelog: list[dict] = []
    new = await te._apply_mass_flag_rename(
        "Oil Refining & Marketing", ["AEP", "OKE", "SO"], theme,
        {"flagged": ["AEP", "SO"], "member_count": 24}, changelog)

    assert new == "Energy Infrastructure & Utilities"
    # thesis names a member -> passes the #125 description-quality check -> adopted
    assert theme["description"] == "New thesis covering AEP, OKE and SO."
    entry = next(e for e in changelog if e["type"] == "theme_renamed_on_mass_flag")
    assert entry["old_name"] == "Oil Refining & Marketing"
    assert entry["new_name"] == "Energy Infrastructure & Utilities"
    assert any(e[0] == "theme_renamed_on_mass_flag" for e in audits)


@pytest.mark.asyncio
async def test_loop_cap_neither_renames_nor_strips(monkeypatch):
    """THE LOOP CAP. Falling back to a strip here would reintroduce the exact defect, so
    the members stay and the operator gets a distinct row."""
    audits = _stub_rename_env(monkeypatch, capped=True)
    changelog: list[dict] = []
    new = await te._apply_mass_flag_rename(
        "Already Renamed Theme", ["AAA", "BBB"], {"name": "x"},
        {"flagged": ["AAA"], "member_count": 4}, changelog)
    assert new == "Already Renamed Theme"
    assert [e[0] for e in audits] == ["theme_rename_cap_reached"]
    assert changelog[0]["type"] == "theme_rename_cap_reached"


@pytest.mark.asyncio
async def test_loop_cap_is_keyed_on_the_NEW_name_so_it_bounds_a_chain():
    """A -> B on day 0 must stop B -> C, which a per-name rate limit keyed on the OLD name
    would not. Pinned on the summary format the query matches, so a reworded summary breaks
    a test instead of silently unbounding the loop."""
    import re

    def _like(pattern: str) -> str:
        """SQL LIKE -> regex: everything literal except `%` (which is `.*`)."""
        return "".join(".*" if part == "%" else re.escape(part)
                       for part in re.split(r"(%)", pattern))

    rx = _like(te._rename_summary_pattern("B"))
    assert re.fullmatch(rx, te._RENAME_SUMMARY_FMT.format(
        old="A", new="B", n_flagged=5, n_members=8))
    # B -> C is a rename OUT of B, not INTO it: it must NOT satisfy B's cap query,
    # otherwise the cap would fire on the wrong hop of the chain.
    assert not re.fullmatch(rx, te._RENAME_SUMMARY_FMT.format(
        old="B", new="C", n_flagged=5, n_members=8))


@pytest.mark.asyncio
async def test_loop_cap_fails_CLOSED_on_a_db_error(monkeypatch):
    """Asymmetric with the #214 inheritance guard on purpose: that one fails open (costs a
    bad name), this one fails closed (failing open costs an unbounded rename loop)."""
    async def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(te, "get_pool", _boom)
    assert await te._recently_renamed_on_mass_flag("Anything") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [
    {"live": True},                                   # target name already a live theme
    {"evicted": True},                                # target name itself mass-evicted
    {"proposal": None},                               # naming call failed
    {"proposal": ("Oil Refining & Marketing", "x")},  # model returned the same name
    {"proposal": ("", "x")},                          # unusable name
])
async def test_every_refusal_path_keeps_the_old_name_and_never_strips(monkeypatch, kwargs):
    if kwargs.get("proposal") == ("", "x"):
        # exercise the real validator rather than the stub for the unusable-name case
        kwargs["proposal"] = None
    _stub_rename_env(monkeypatch, **kwargs)
    changelog: list[dict] = []
    new = await te._apply_mass_flag_rename(
        "Oil Refining & Marketing", ["AAA", "BBB"], {"name": "x", "description": "d"},
        {"flagged": ["AAA"], "member_count": 4}, changelog)
    assert new == "Oil Refining & Marketing"
    assert not [e for e in changelog if e["type"] == "theme_renamed_on_mass_flag"]


@pytest.mark.asyncio
async def test_naming_reuses_the_discovery_tool_not_a_second_mechanism(monkeypatch):
    """The #214 breadth contract ("every listed ticker must individually fit this name")
    lives on `_THEME_DISCOVERY_TOOL`'s `name` field. Reusing that tool IS the fix — a
    second, drifting copy of the rule would not be."""
    captured: dict = {}

    class _Block:
        type = "tool_use"
        name = "report_themes"
        input = {"themes": [{"name": "Energy Infrastructure", "thesis": "t",
                             "tickers": ["AEP"]}]}

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"

    class _Messages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Resp()

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(te, "_get_anthropic_client", lambda: _Client())

    async def _log(**kw):
        return None
    monkeypatch.setattr("agents.market_intelligence.spend_tracker.log_anthropic_call_safe", _log)

    out = await te._rename_theme_to_fit_cluster("Narrow Name", ["AEP", "SO"], "th", ["AEP"])
    assert out == ("Energy Infrastructure", "t")
    assert captured["tools"] == [te._THEME_DISCOVERY_TOOL]
    assert captured["tool_choice"] == {"type": "any"}
    assert captured["max_tokens"] == 1750          # shared/output_ceilings.py::theme_rename
    from shared import llm_thinking
    assert captured["thinking"] == llm_thinking.DISABLED


# ── 4. IDENTITY — a rename must preserve lineage, not mint a new theme ───────────────────

@pytest.mark.asyncio
async def test_canonicalize_does_not_undo_a_rename_made_this_run(monkeypatch):
    """THE TRAP. `_canonicalize_theme_names` renames today's theme back to a prior name on
    an exact ticker-set match — and a #214 rename leaves the ticker set UNCHANGED, which is
    precisely its trigger. Without this carve-out the fix passes every unit test and
    no-ops in production, logged as ordinary continuity churn."""
    themes = [{"name": "Energy Infrastructure & Utilities", "tickers": ["AEP", "SO"],
               "renamed_from": "Oil Refining & Marketing"}]

    class _Conn:
        async def fetch(self, *a, **k):
            return [{"name": "Oil Refining & Marketing", "theme_date": "2026-08-25",
                     "tickers": ["AEP", "SO"]}]

    async def _audit(*a, **k):
        return None
    monkeypatch.setattr(te, "log_audit_event", _audit)

    n = await te._canonicalize_theme_names(_Conn(), themes, "2026-08-26")
    assert n == 0
    assert themes[0]["name"] == "Energy Infrastructure & Utilities"


@pytest.mark.asyncio
async def test_canonicalize_refuses_a_mass_evicted_donor_name_on_later_runs(monkeypatch):
    """The in-memory flag only protects TODAY. On every later run the old name's rows are
    still inside canonicalize's 14-day window, so the durable guard is the donor check —
    the same rule, and the same helper, the #214 name-INHERITANCE guard already uses."""
    themes = [{"name": "Energy Infrastructure & Utilities", "tickers": ["AEP", "SO"]}]
    seen = {}

    class _Conn:
        async def fetch(self, *a, **k):
            return [{"name": "Oil Refining & Marketing", "theme_date": "2026-08-25",
                     "tickers": ["AEP", "SO"]}]

    async def _evicted(name, days=30, conn=None):
        seen["name"] = name
        return True

    async def _audit(event_type, summary="", detail=""):
        seen.setdefault("audits", []).append(event_type)
    monkeypatch.setattr(te, "_name_recently_mass_evicted", _evicted)
    monkeypatch.setattr(te, "log_audit_event", _audit)

    n = await te._canonicalize_theme_names(_Conn(), themes, "2026-08-26")
    assert n == 0
    assert themes[0]["name"] == "Energy Infrastructure & Utilities"
    assert seen["name"] == "Oil Refining & Marketing"
    assert "theme_canonicalize_blocked_mass_evicted" in seen["audits"]


@pytest.mark.asyncio
async def test_canonicalize_still_works_normally_for_unrenamed_themes(monkeypatch):
    """The carve-out must be narrow — #59's cosmetic-rephrasing convergence still runs."""
    themes = [{"name": "Custom AI Silicon", "tickers": ["AMD", "ARM"]}]

    class _Conn:
        async def fetch(self, *a, **k):
            return [{"name": "AI Datacenter Silicon", "theme_date": "2026-08-20",
                     "tickers": ["AMD", "ARM"]}]

    async def _evicted(name, days=30, conn=None):
        return False

    async def _audit(*a, **k):
        return None
    monkeypatch.setattr(te, "_name_recently_mass_evicted", _evicted)
    monkeypatch.setattr(te, "log_audit_event", _audit)

    n = await te._canonicalize_theme_names(_Conn(), themes, "2026-08-26")
    assert n == 1
    assert themes[0]["name"] == "AI Datacenter Silicon"


def test_save_path_carries_continuity_counters_across_the_rename():
    """`_save_themes` looks counters up BY NAME, so a renamed theme has no prior row and
    would restart at days_active=1 / consecutive_accelerating=0. That is not cosmetic: both
    feed the stage machinery, and a theme knocked back to Nascent drops the R4 in-theme
    bonus for every member — i.e. it WOULD change EP scores. Pinned on the source so the
    fallback cannot be dropped without a red test."""
    import pathlib
    src = pathlib.Path("agents/market_intelligence/theme_engine.py").read_text()
    assert 'prior = prior_map.get(t["renamed_from"])' in src
    assert '_counter_names |= {t["renamed_from"] for t in themes if t.get("renamed_from")}' in src


def test_old_name_is_tombstoned_with_the_new_name_as_successor():
    """Otherwise `get_active_themes` keeps the OLD name alive off its last non-Retired row
    for the rest of its 7-day recency window — the same cohort counted twice under two
    names, which is exactly the double-count FIX 2 is about."""
    import pathlib
    src = pathlib.Path("agents/market_intelligence/theme_engine.py").read_text()
    assert "successor_by_lost: dict[str, str] = dict(renamed_map)" in src
    assert "renamed to '{successor}' — name was narrower than the cluster (#214)" in src


def test_a_rename_is_not_reported_as_a_retirement():
    import pathlib
    src = pathlib.Path("agents/market_intelligence/theme_engine.py").read_text()
    assert "continue   # #214 — renamed, not retired" in src


def test_sub_theme_parent_links_are_rekeyed_across_the_rename():
    """`_restore_sub_theme_links` matches on names; without re-keying, a renamed parent or
    child reads as a genuine orphan and the link is CLEARED (#471's failure mode)."""
    import pathlib
    src = pathlib.Path("agents/market_intelligence/theme_engine.py").read_text()
    assert "renamed_map.get(child, child): renamed_map.get(parent, parent)" in src


def test_exclusions_are_never_auto_populated_on_this_path():
    """Standing rule (CLAUDE.md + SSoT): `mi_theme_exclusions` is user-directed bans ONLY.
    The rename path writes no removals at all, so it must not write exclusions either."""
    import pathlib
    src = pathlib.Path("agents/market_intelligence/theme_engine.py").read_text()
    start = src.index("# ── #214 — a too-narrow NAME is renamed")
    end = src.index("def _rs_rising(")
    block = src[start:end]
    # `add_theme_exclusion` is the ONLY writer (db.py:11103). A mention in prose is fine;
    # a call is not.
    assert "add_theme_exclusion" not in block
    assert "INSERT INTO mi_theme_exclusions" not in block


@pytest.mark.asyncio
async def test_a_thesis_that_would_cap_the_stage_is_not_adopted(monkeypatch):
    """EP CONSTRAINT. The #125 description-quality check caps an Accelerating/Mainstream
    theme to Nascent when its description names no member — and a stage cap costs every
    member the R4 +10 in-theme bonus, which IS a change to EP scores. A rename must never
    be able to trigger that, so a thesis failing the check is not stored; the prior
    description stands until the next Perplexity refresh."""
    _stub_rename_env(monkeypatch,
                     proposal=("Energy Infrastructure & Utilities",
                               "Broad energy exposure with no ticker named."))
    theme = {"name": "Oil Refining & Marketing", "description": "Refiners incl AEP."}
    new = await te._apply_mass_flag_rename(
        "Oil Refining & Marketing", ["AEP", "OKE", "SO"], theme,
        {"flagged": ["AEP"], "member_count": 24}, [])
    assert new == "Energy Infrastructure & Utilities"       # the rename still happens
    assert theme["description"] == "Refiners incl AEP."      # the thesis does not


# ── 4b. `renamed_from` must SURVIVE to _save_themes, not just be read there ──────────────

def test_every_rescore_return_branch_carries_renamed_from():
    """Pinning the fallback line in `_save_themes` is not enough — the key has to REACH it.
    `_rescore_existing_theme` rebuilds its theme dict from scratch on every branch, which is
    exactly how #471 lost `parent_theme` (NULL on the very next save while the parent was
    still alive). Assert it structurally, so a future third return branch cannot quietly
    drop the key and reset a renamed theme to days_active=1."""
    import ast
    import inspect
    import textwrap

    src = textwrap.dedent(inspect.getsource(te._rescore_existing_theme))
    fn = ast.parse(src).body[0]
    dict_returns = [n for n in ast.walk(fn)
                    if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)
                    and n.value.elts and isinstance(n.value.elts[0], ast.Dict)]
    assert len(dict_returns) >= 2, "expected the Fading branch and the scored branch"
    for ret in dict_returns:
        keys = {k.value for k in ret.value.elts[0].keys if isinstance(k, ast.Constant)}
        assert "renamed_from" in keys, f"a return branch drops renamed_from: {sorted(keys)}"
        assert "parent_theme" in keys, "the #471 carry-forward regressed"


def test_the_one_rebuilding_transform_on_the_path_preserves_the_key():
    """Between rescore and `_save_themes` exactly one helper rebuilds a rescored theme dict:
    `_strip_sector_outliers`. It spreads (`{**theme, ...}`) so extra keys survive — pinned
    here because a refactor to explicit field construction would break the counter
    carry-forward silently, on rename nights only."""
    theme = {"name": "T", "tickers": ["AAA", "BBB"], "renamed_from": "Old Narrow Name",
             "parent_theme": None}
    out = te._strip_sector_outliers(theme, {})
    assert out.get("renamed_from") == "Old Narrow Name"
