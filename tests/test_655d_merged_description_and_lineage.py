"""#655 (d) follow-on, his ruling 2026-10-17 ("Yes"): a renaming Arm B merge STORES the merged
validation text as the theme's description, and an Arm B rename WRITES a #601 lineage row.

Two changes, both only on the `adopt_merged` branch of `_run_thesis_merge_pass`:

  1. The merged theme's stored description = exactly `_merged_validation_thesis(winner, absorbed)`
     (the text the union was just validated against) - BUT ONLY IF it passes the #125
     description-quality check the #214 rename path applies before it adopts a fresh thesis
     (`_check_description_quality(merged name, surviving members, text)`). `None` (no usable
     description on either side) or a failing text keeps the winner's old one, and the
     `theme_thesis_merged` audit row says which (`description_stored=False (description quality
     check: <rule>)`). It must reach `mi_themes` - proved here through the REAL `_save_themes`
     against an in-memory store, not by reading a dict field.
  2. An adopted rename stages `arm_b_renamed_from` on the theme; `_save_themes` writes the
     `old winner -> merged name` edge with `record_theme_rename` (mechanism `arm_b_merge_rename`)
     on the connection that lands the merged theme's row. NOT `renamed_from`: that flag also
     carries day counters, skips canonicalize / the small fold / the weak-Fading retire, and
     is recorded under the #214 mechanism.

The cross-run case is the point of (2): a `/bypass` filed under the winner's OLD name must protect
the member under the MERGED name on a LATER night, through the REAL `get_operator_protected_set`,
reading only what the first night persisted - with the no-lineage negative control showing the same
later night loses it.
"""
from __future__ import annotations

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import theme_engine as te
from tests.test_theme_rename_lineage_601 import _llm_flags, _Pool, _Store
from tests.test_theme_thesis_merge_pass import (
    ABSORBED_NAME, APPAREL, FURNITURE, MERGED_NAME, OLD_NAME, TODAY, _furniture_and_apparel,
    _merge_verdict, _name_aware_validator, _pair_them, _t, _wire,
)

_REAL_VALIDATE = te._validate_theme_membership   # captured before any test monkeypatches it
GARBAGE = "No specific news found for this theme"
SECOND_MERGED_NAME = "Consumer Discretionary Cyclical Rebound & Household Goods"


def _named_pair():
    """The shared fixture pair with a member ticker NAMED in each description - the shape that
    passes the #125 quality check (Rule B: at least one member mentioned). `_furniture_and_apparel`
    names none, so on its own the merged text fails the guard (pinned below). A comma between the
    symbols: `F1 F2` adjacent would trip Rule A (concat)."""
    themes = _furniture_and_apparel()
    themes[0]["description"] = ("Office, home and commercial furniture demand (F1, F2) tied to housing "
                                "and office fit-outs")
    themes[1]["description"] = ("Mall-based apparel and footwear retailers (A1, A2) recovering on "
                                "consumer spending")
    return themes


# ── an in-memory DB that persists ACROSS "nights" (the #601 harness) ───────────────────────

@pytest.fixture
def store(monkeypatch):
    st = _Store()
    pool = _Pool(st)

    async def _gp():
        return pool
    monkeypatch.setattr(te, "get_pool", _gp)       # `_save_themes` resolves it in theme_engine
    monkeypatch.setattr(db, "get_pool", _gp)       # the ruling loaders and record_theme_rename in db

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(te, "_emit_cross_run_dup_probe", _noop)
    monkeypatch.setattr(te, "_canonicalize_theme_names", _noop)
    return st


async def _run_pass(monkeypatch, themes, *, merged_name=MERGED_NAME, validate=None, protected=None,
                    calls=None, events=None, details=None):
    got_events, _cd = _wire(monkeypatch, _merge_verdict(merged_name),
                            validate=validate or _name_aware_validator(), calls=calls, details=details)
    if events is not None:
        events.extend(got_events)   # same list object is appended to by the fake audit
    _pair_them(monkeypatch)
    return await te._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], protected, TODAY), got_events


def _mi_themes_description(store, name):
    rows = [args for sql, args in store.executed if "INSERT INTO mi_themes" in sql and args[1] == name]
    assert len(rows) >= 1, f"no mi_themes row was written for {name!r}"
    return rows[-1][5]


def _edges(store):
    return [(r[0], r[1], r[2], r[4]) for r in store.renames]   # (old, new, mechanism, theme_date)


# ── 1. the stored description ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_renaming_merge_stores_exactly_the_validation_text(monkeypatch):
    calls: list[dict] = []
    themes = _named_pair()
    expected = te._merged_validation_thesis(themes[0], themes[1])
    old_desc = themes[0]["description"]
    out, _ = await _run_pass(monkeypatch, themes, calls=calls)

    merged = next(t for t in out if t["name"] == MERGED_NAME)
    assert merged["description"] == expected == calls[0]["thesis"]   # the text the union was judged on
    assert merged["description"] != old_desc                          # not the winner's old narrow one
    assert len(merged["description"]) <= 300                          # the validator window


@pytest.mark.asyncio
async def test_the_stored_description_reaches_mi_themes_through_the_real_save(monkeypatch, store):
    """The failure to avoid: a field set on a dict that no save path ever writes. The REAL
    `_save_themes` runs against the in-memory store and the INSERT's description argument is read back."""
    calls: list[dict] = []
    out, _ = await _run_pass(monkeypatch, _named_pair(), calls=calls)
    await te._save_themes(out)

    assert _mi_themes_description(store, MERGED_NAME) == calls[0]["thesis"]
    assert "|" in calls[0]["thesis"]            # it really is the joined two-half text


@pytest.mark.asyncio
async def test_no_usable_description_on_either_side_leaves_the_winners_unchanged(monkeypatch, store):
    """`_merged_validation_thesis` -> None (both blurbs are garbage): nothing is stored over the
    winner's own description - and the rename itself is still real, so its lineage edge still lands."""
    calls: list[dict] = []
    themes = _furniture_and_apparel()
    themes[0]["description"] = GARBAGE
    themes[1]["description"] = GARBAGE
    out, _ = await _run_pass(monkeypatch, themes, calls=calls)
    await te._save_themes(out)

    assert calls[0]["thesis"] is None
    merged = next(t for t in out if t["name"] == MERGED_NAME)
    assert merged["description"] == GARBAGE                                  # unchanged, not blanked
    assert _mi_themes_description(store, MERGED_NAME) == GARBAGE
    assert [(e[0], e[1]) for e in _edges(store)] == [(OLD_NAME, MERGED_NAME)]


@pytest.mark.asyncio
@pytest.mark.parametrize("merged_name", ["", OLD_NAME, ABSORBED_NAME])
async def test_a_non_renaming_merge_changes_neither_description_nor_lineage(monkeypatch, store, merged_name):
    """No merged name / the winner's own / a colliding one: byte-for-byte today - the winner keeps
    its own description, nothing is staged on it, no lineage row is written."""
    themes = _furniture_and_apparel()
    winner_desc = themes[0]["description"]
    out, events = await _run_pass(monkeypatch, themes, merged_name=merged_name)
    await te._save_themes(out)

    live = next(t for t in out if t["name"] == OLD_NAME and t["stage"] != "Retired")
    assert live["description"] == winner_desc
    assert "arm_b_renamed_from" not in live
    assert store.renames == []
    assert _mi_themes_description(store, OLD_NAME) in (winner_desc, "")     # the Retired tombstone shares the name


@pytest.mark.asyncio
async def test_a_gutted_renamed_merge_stores_nothing_and_stages_no_lineage(monkeypatch, store):
    async def gut(name, tickers):
        return tickers[:1]

    themes = _furniture_and_apparel()
    winner_desc = themes[0]["description"]
    out, _ = await _run_pass(monkeypatch, themes, validate=gut)
    await te._save_themes(out)

    assert all(t["name"] != MERGED_NAME for t in out)                       # the merged name never exists
    assert themes[0]["description"] == winner_desc and "arm_b_renamed_from" not in themes[0]
    assert store.renames == []


def _desc_note(details):
    """The `theme_thesis_merged` audit detail's description clause (the verify-live evidence)."""
    rows = [d for e, d in details if e == "theme_thesis_merged"]
    assert len(rows) == 1
    return rows[0]


@pytest.mark.asyncio
async def test_a_merged_text_that_passes_the_quality_check_is_stored_and_the_audit_says_so(
        monkeypatch, store):
    details: list = []
    out, _ = await _run_pass(monkeypatch, _named_pair(), details=details)
    await te._save_themes(out)

    merged = next(t for t in out if t["name"] == MERGED_NAME)
    assert "|" in merged["description"] and merged["description"] != _named_pair()[0]["description"]
    assert _mi_themes_description(store, MERGED_NAME) == merged["description"]
    assert "description_stored=True (description quality check: ok)" in _desc_note(details)


@pytest.mark.asyncio
@pytest.mark.parametrize("winner_desc, absorbed_desc, rule", [
    # Rule B: neither half names a member ticker (the shared fixture's own descriptions)
    ("Office, home and commercial furniture demand tied to housing and office fit-outs",
     "Mall-based apparel and footwear retailers recovering on consumer spending",
     "no_member_ticker_mentioned"),
    # Rule A: two member symbols run together read as one entity ('LOVE SEAT')
    ("Office furniture names F1 F2 tied to housing", "Apparel retailers recovering",
     "ticker_concat:F1_F2"),
])
async def test_a_merged_text_that_fails_the_quality_check_is_not_stored(
        monkeypatch, store, winner_desc, absorbed_desc, rule):
    """The guard (his ruling's intent kept: the merged theme keeps its members and its new name; only
    the TEXT is held back). The winner's own description stays - today's behaviour, byte for byte - the
    rename and its lineage edge still land, and the audit row carries the failing rule."""
    details: list = []
    calls: list[dict] = []
    themes = _furniture_and_apparel()
    themes[0]["description"], themes[1]["description"] = winner_desc, absorbed_desc
    out, _ = await _run_pass(monkeypatch, themes, calls=calls, details=details)
    await te._save_themes(out)

    assert "|" in calls[0]["thesis"]                                   # it WAS judged on the joined text
    merged = next(t for t in out if t["name"] == MERGED_NAME)
    assert merged["description"] == winner_desc                        # ...but not stored
    assert _mi_themes_description(store, MERGED_NAME) == winner_desc
    assert set(merged["tickers"]) == set(FURNITURE + APPAREL)           # members untouched
    assert [(e[0], e[1]) for e in _edges(store)] == [(OLD_NAME, MERGED_NAME)]   # rename + lineage still land
    assert f"description_stored=False (description quality check: {rule})" in _desc_note(details)


@pytest.mark.asyncio
async def test_the_quality_check_judges_the_surviving_members_not_the_pre_validation_union(
        monkeypatch, store):
    """Mirrors #214 (`_check_description_quality(new_name, tickers, thesis)` over the members that
    REMAIN): a text naming only a member the validator stripped names no member of the merged theme."""
    details: list = []
    themes = _furniture_and_apparel(extra_apparel=["X1"])               # X1 fits neither name: stripped
    themes[0]["description"] = "Furniture demand and the X1 bank lender, tied to housing"
    out, _ = await _run_pass(monkeypatch, themes, details=details)

    merged = next(t for t in out if t["name"] == MERGED_NAME)
    assert "X1" not in merged["tickers"]
    assert merged["description"] == "Furniture demand and the X1 bank lender, tied to housing"   # kept, not merged text
    assert "description_stored=False (description quality check: no_member_ticker_mentioned)" in _desc_note(details)


@pytest.mark.asyncio
async def test_no_usable_description_reads_empty_description_in_the_audit_row(monkeypatch, store):
    details: list = []
    themes = _furniture_and_apparel()
    themes[0]["description"] = GARBAGE
    themes[1]["description"] = GARBAGE
    await _run_pass(monkeypatch, themes, details=details)
    assert "description_stored=False (description quality check: empty_description)" in _desc_note(details)


# ── 2. the lineage row ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_lineage_row_is_written_once_with_the_right_names(monkeypatch, store):
    out, _ = await _run_pass(monkeypatch, _furniture_and_apparel())
    await te._save_themes(out)

    assert _edges(store) == [(OLD_NAME, MERGED_NAME, db.THEME_RENAME_MECHANISM_ARM_B_MERGE, TODAY)]
    assert db.THEME_RENAME_MECHANISM_ARM_B_MERGE != db.THEME_RENAME_MECHANISM_MASS_FLAG   # truthful label
    detail = store.renames[0][3]
    assert "Arm B" in detail and "#214" not in detail
    # absorption is not a rename: nothing is written for the absorbed theme's name
    assert all(r[0] != ABSORBED_NAME and r[1] != ABSORBED_NAME for r in store.renames)

    await te._save_themes(out)                                              # the same-night re-run
    assert len(store.renames) == 1


@pytest.mark.asyncio
async def test_arm_b_does_not_set_the_214_renamed_from_flag(monkeypatch):
    """`renamed_from` would also carry the old name's day counters, skip canonicalize / the small
    fold / the weak-Fading retire and be recorded as a mass-flag rename - none of which is this."""
    out, _ = await _run_pass(monkeypatch, _furniture_and_apparel())
    merged = next(t for t in out if t["name"] == MERGED_NAME)
    assert not merged.get("renamed_from")
    assert merged["arm_b_renamed_from"] == [OLD_NAME]


def _two_pairs_one_winner(second_merged_name):
    """One winner (the furniture theme) wins two pairs in a night."""
    themes = _furniture_and_apparel()
    other = _t("Household Goods Retail", ["H1", "H2"], 40)
    themes.append(other)
    verdicts = {
        ABSORBED_NAME: {"verdict": "MERGE", "driver_a": "c", "driver_b": "c", "reason": "r",
                        "merged_name": MERGED_NAME},
        other["name"]: {"verdict": "MERGE", "driver_a": "c", "driver_b": "c", "reason": "r",
                        "merged_name": second_merged_name},
    }
    return themes, verdicts


@pytest.mark.asyncio
async def test_a_winner_that_wins_twice_in_a_night_records_every_name_it_carried(monkeypatch, store):
    """One winner can win two pairs (3 merges/night): the second rename starts from the FIRST merged
    name, so a single-valued field would silently lose the name the operator actually ruled under.
    The same holds for tonight's PROTECTION: a `/bypass` filed under the ORIGINAL name has no lineage
    edge yet (`_save_themes` writes them after the pass), so the second validation - run under the
    second merged name - must still be handed it."""
    themes, verdicts = _two_pairs_one_winner(SECOND_MERGED_NAME)
    calls: list[dict] = []
    _wire(monkeypatch, verdicts, calls=calls)
    monkeypatch.setattr(te, "propose_merge_pairs",
                        lambda cands, **kw: [(cands[0], cands[1]), (cands[0], cands[2])])
    bypass = {("F2", OLD_NAME), ("ZZ", "Some Other Theme")}          # filed under the ORIGINAL name
    out = await te._run_thesis_merge_pass(themes, {t["name"] for t in themes}, [], bypass, TODAY)
    await te._save_themes(out)

    live = [t["name"] for t in out if t["stage"] != "Retired"]
    assert live == [SECOND_MERGED_NAME]
    assert sorted((e[0], e[1]) for e in _edges(store)) == sorted(
        [(OLD_NAME, SECOND_MERGED_NAME), (MERGED_NAME, SECOND_MERGED_NAME)])
    assert [c["name"] for c in calls] == [MERGED_NAME, SECOND_MERGED_NAME]
    assert ("F2", MERGED_NAME) in calls[0]["protected"]
    assert ("F2", SECOND_MERGED_NAME) in calls[1]["protected"]       # the original name's ruling, carried twice
    assert ("ZZ", SECOND_MERGED_NAME) not in calls[1]["protected"]   # only the winner's own names move
    assert ("F2", OLD_NAME) in calls[1]["protected"]                 # nothing dropped


@pytest.mark.asyncio
async def test_a_second_win_that_adopts_no_name_still_carries_the_earlier_names(monkeypatch, store):
    """The non-adopt branch of the same night: the second pair's adjudicator proposes no new name, so the
    winner (already named MERGED_NAME by its first win) is validated under THAT name - which no ruling was
    ever filed under. A `/bypass` under the ORIGINAL name must reach that call too."""
    themes, verdicts = _two_pairs_one_winner("")
    calls: list[dict] = []
    _wire(monkeypatch, verdicts, calls=calls)
    monkeypatch.setattr(te, "propose_merge_pairs",
                        lambda cands, **kw: [(cands[0], cands[1]), (cands[0], cands[2])])
    out = await te._run_thesis_merge_pass(
        themes, {t["name"] for t in themes}, [], {("F2", OLD_NAME)}, TODAY)

    assert [c["name"] for c in calls] == [MERGED_NAME, MERGED_NAME]   # no second rename
    assert ("F2", MERGED_NAME) in calls[1]["protected"]
    assert [t["name"] for t in out if t["stage"] != "Retired"] == [MERGED_NAME]
    assert next(t for t in out if t["name"] == MERGED_NAME)["arm_b_renamed_from"] == [OLD_NAME]


@pytest.mark.asyncio
async def test_a_first_win_that_adopts_no_name_passes_the_protected_set_through_untouched(monkeypatch):
    """The non-adopt path stays byte-for-byte today's when the winner has not renamed tonight: the very
    object (and `None`, which the validator re-fetches itself) goes through, no carry, no fetch."""
    sentinel = {("F2", OLD_NAME)}
    for given in (sentinel, None):
        calls: list[dict] = []
        await _run_pass(monkeypatch, _furniture_and_apparel(), merged_name="", protected=given, calls=calls)
        assert calls[0]["protected"] is given


@pytest.mark.asyncio
async def test_a_failed_lineage_write_is_loud_and_does_not_abort_the_save(monkeypatch, store):
    async def boom(*a, **k):
        raise RuntimeError("disk full")

    out, events = await _run_pass(monkeypatch, _furniture_and_apparel())
    monkeypatch.setattr(te, "record_theme_rename", boom)
    await te._save_themes(out)

    assert _mi_themes_description(store, MERGED_NAME)                       # the row still landed
    failed = [s for e, s in events if e == "theme_rename_lineage_write_failed"]
    assert len(failed) == 1 and OLD_NAME in failed[0] and MERGED_NAME in failed[0]


# ── 3. THE ACCEPTANCE CASE - a later night, through the real loader ───────────────────────

@pytest.mark.asyncio
async def test_FAILS_WITHOUT_FIX_a_bypass_under_the_old_name_protects_under_the_merged_name_next_night(
        monkeypatch, store):
    """Night 1: the merge renames the furniture theme and `_save_themes` persists it. Night 2 is a
    fresh process: the REAL `get_operator_protected_set` reads only what night 1 persisted."""
    store.protected |= {("F2", OLD_NAME), ("ZZ", "Some Other Theme")}
    out, _ = await _run_pass(monkeypatch, _furniture_and_apparel(), protected=set(store.protected))
    await te._save_themes(out)

    night2 = await db.get_operator_protected_set()
    assert ("F2", MERGED_NAME) in night2 and ("F2", OLD_NAME) in night2
    assert ("ZZ", MERGED_NAME) not in night2                                 # only the winner's lineage moves


@pytest.mark.asyncio
async def test_negative_control_without_the_lineage_row_night_2_loses_the_ruling(monkeypatch, store):
    """The defect, reproduced: the same night 1 without the staged edge (the pre-fix world)."""
    store.protected.add(("F2", OLD_NAME))
    out, _ = await _run_pass(monkeypatch, _furniture_and_apparel(), protected=set(store.protected))
    for t in out:
        t.pop("arm_b_renamed_from", None)
    await te._save_themes(out)

    assert store.renames == []
    assert ("F2", MERGED_NAME) not in await db.get_operator_protected_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("with_lineage", [True, False])
async def test_night_2_the_real_validator_keeps_the_member_the_model_flags(monkeypatch, store, with_lineage):
    """End to end on night 2: the REAL validator is asked about the merged name with
    `protected=None` (its own fallback fetch), the model flags F2, and the ruling filed under the
    OLD name still shields it - no cooldown is written against it. `with_lineage=False` is the
    control: without the edge the very same call strips F2 and files a cooldown (the defect)."""
    store.protected.add(("F2", OLD_NAME))
    out, _ = await _run_pass(monkeypatch, _furniture_and_apparel(), protected=set(store.protected))
    if not with_lineage:
        for t in out:
            t.pop("arm_b_renamed_from", None)
    await te._save_themes(out)

    written: list[tuple[str, str]] = []

    async def _cooldown(tk, theme, reason=""):
        written.append((tk, theme))
        return 1

    async def _audit(event_type, summary="", detail=""):
        return None
    monkeypatch.setattr(te, "add_validation_cooldown", _cooldown)
    monkeypatch.setattr(te, "log_audit_event", _audit)
    monkeypatch.setattr(db, "log_audit_event", _audit)
    # `_wire` stubbed the loader to an empty set for night 1; night 2 must use the REAL one.
    monkeypatch.setattr(te, "get_operator_protected_set", db.get_operator_protected_set)
    _llm_flags(monkeypatch, ["F2"])
    survivors = await _REAL_VALIDATE(MERGED_NAME, FURNITURE + APPAREL, changelog=[], protected=None)

    if with_lineage:
        assert "F2" in survivors
        assert ("F2", MERGED_NAME) not in written and ("F2", OLD_NAME) not in written
    else:
        assert "F2" not in survivors and ("F2", MERGED_NAME) in written


@pytest.mark.asyncio
async def test_side_effect_a_ban_filed_under_the_old_name_now_also_covers_the_merged_theme(
        monkeypatch, store):
    """Stated, not hidden: `get_all_theme_exclusions` expands across the same lineage, so an
    `mi_theme_exclusions` ban filed under the winner's old name now also bans that ticker from the
    merged theme. Truthful (the merged theme IS the renamed winner) and read-side only."""
    store.exclusions.add(("CAR", OLD_NAME))
    before = await db.get_all_theme_exclusions()
    assert te._get_excluded_tickers_for_theme(MERGED_NAME, before) == set()

    out, _ = await _run_pass(monkeypatch, _furniture_and_apparel())
    await te._save_themes(out)
    after = await db.get_all_theme_exclusions()
    assert te._get_excluded_tickers_for_theme(MERGED_NAME, after) == {"CAR"}
    assert [sql for sql, _ in store.executed if "INSERT INTO mi_theme_exclusions" in sql] == []
