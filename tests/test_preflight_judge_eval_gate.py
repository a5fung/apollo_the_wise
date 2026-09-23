"""Preflight [5m/7] pins — the grade-quality regression gate (ADR 0030 §4)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "preflight_judge_eval_gate",
    Path(__file__).parent.parent / "scripts" / "preflight_judge_eval_gate.py",
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

LIVE = {"rubric_version": "v3", "rubric_hash": "aaaa1111",
        "catalyst_grade_prompt_version": "v3", "judge_model": "claude-opus-4-8",
        "corpus_sha1": "cafe00112233"}


def _rec(**over):
    r = {**LIVE, "pass": True, "waiver": None, "run_at": "2026-07-12"}
    r.update(over)
    return r


def test_match_passes():
    ok, _ = gate.check(_rec(), LIVE)
    assert ok is True


def test_missing_record_fails():
    ok, msgs = gate.check(None, LIVE)
    assert ok is False
    assert any("no pass record" in m for m in msgs)


def test_rubric_hash_mismatch_fails():
    ok, msgs = gate.check(_rec(rubric_hash="bbbb2222"), LIVE)
    assert ok is False
    assert any("rubric_hash" in m for m in msgs)


def test_model_swap_fails():
    ok, _ = gate.check(_rec(judge_model="claude-sonnet-5"), LIVE)
    assert ok is False


def test_corpus_content_edit_fails():
    ok, _ = gate.check(_rec(corpus_sha1="dead00000000"), LIVE)
    assert ok is False


def test_record_pass_false_fails_even_when_keys_match():
    ok, msgs = gate.check(_rec(**{"pass": False}), LIVE)
    assert ok is False
    assert any("record.pass is not true" in m for m in msgs)


def test_waiver_passes_loudly():
    ok, msgs = gate.check(_rec(rubric_hash="bbbb2222", waiver="emergency deploy, operator 7/12"),
                          LIVE)
    assert ok is True
    assert any("WAIVED" in m for m in msgs)


def test_extract_live_keys_matches_the_real_module_hash():
    # the ast-recomputed hash must equal the module's own RUBRIC_HASH (import-free parity)
    live = gate.extract_live_keys()
    from agents.market_intelligence.ep_grade_judge import RUBRIC_HASH, RUBRIC_VERSION
    from shared.llm_models import JUDGE_MODEL
    assert live["rubric_hash"] == RUBRIC_HASH
    assert live["rubric_version"] == RUBRIC_VERSION
    assert live["judge_model"] == JUDGE_MODEL


# ── #547 / ADR 0030 — the ENVELOPE fingerprint (max_tokens/timeout/tool_choice/fail-open) ──
# Separate signal by operator ruling 2026-08-13: must flag loudly + name old->new, must NEVER
# set the eval-rerun trigger. These tests prove that independence behaviourally, not just by
# code inspection — a test that would pass with AND without the separation is not a test here.

ENV_LIVE = {"max_tokens": 1500, "timeout": 25, "tool_choice_type": "tool",
            "fail_open_hash": "aaaa11112222"}


def _env_baseline(**over):
    b = dict(ENV_LIVE)
    b.update(over)
    return b


def test_envelope_changed_flags_loudly_and_names_old_new_value():
    changed, msgs = gate.check_envelope(_env_baseline(max_tokens=500), ENV_LIVE)
    assert changed is True
    joined = "\n".join(msgs)
    assert "max_tokens: 500 -> 1500" in joined
    # loud, and explicitly says it does not trigger the paid eval
    assert "CHANGED" in joined
    assert "does NOT trigger the paid eval" in joined


def test_envelope_unchanged_is_a_quiet_pass_not_the_loud_banner():
    changed, msgs = gate.check_envelope(_env_baseline(), ENV_LIVE)
    assert changed is False
    joined = "\n".join(msgs)
    assert "unchanged" in joined
    assert "CHANGED" not in joined


def test_envelope_baseline_missing_reads_as_unverified_not_unchanged():
    changed, msgs = gate.check_envelope(None, ENV_LIVE)
    assert changed is False
    joined = "\n".join(msgs)
    assert "UNVERIFIED" in joined
    assert "cannot compare" in joined
    # must NOT be the same sentence the quiet unchanged-pass prints (the #173 "reads as pass" trap)
    _, quiet_msgs = gate.check_envelope(_env_baseline(), ENV_LIVE)
    assert joined != "\n".join(quiet_msgs)


def test_envelope_changed_does_not_set_the_rerun_trigger_a_and_c_independent():
    """The exact (a)/(c) independence proof: same rubric+model+corpus, different envelope ->
    check() still passes (no rerun) while check_envelope() flags. And the mirror: envelope
    unchanged, rubric changed -> check() still fails exactly as today while check_envelope()
    stays quiet. Neither function's outcome moves the other's."""
    record = _rec()  # rubric/model/corpus match LIVE
    record["envelope"] = _env_baseline(max_tokens=500)  # envelope does NOT match

    ok, _ = gate.check(record, LIVE)
    env_changed, _ = gate.check_envelope(record.get("envelope"), ENV_LIVE)
    assert ok is True          # (a) — envelope drift never sets the rerun trigger
    assert env_changed is True  # the drift is still visible

    record2 = _rec(rubric_hash="bbbb2222")  # rubric mismatch -> rerun trigger fires
    record2["envelope"] = _env_baseline()   # envelope matches

    ok2, _ = gate.check(record2, LIVE)
    env_changed2, _ = gate.check_envelope(record2.get("envelope"), ENV_LIVE)
    assert ok2 is False          # (c) — rubric drift still fires the rerun trigger, unchanged
    assert env_changed2 is False  # and the envelope signal stays quiet — no cross-talk


def test_extract_live_keys_key_set_is_exactly_the_rerun_trigger_keys():
    # pins that no envelope key can ever leak into the dict that DRIVES the paid-eval trigger —
    # a future edit that merged the two dicts would silently turn every ceiling tweak into a
    # forced rerun, exactly what the operator's 2026-08-13 ruling forbids.
    assert set(gate.extract_live_keys().keys()) == {
        "rubric_version", "rubric_hash", "catalyst_grade_prompt_version",
        "judge_model", "corpus_sha1",
    }


def test_extract_envelope_keys_matches_the_real_registry_and_live_call_site():
    # import-free parity, mirroring test_extract_live_keys_matches_the_real_module_hash above
    live_env = gate.extract_envelope_keys()
    from shared.output_ceilings import max_tokens_for
    assert live_env["max_tokens"] == max_tokens_for("ep_grade_judge")
    assert live_env["timeout"] == 25          # ep_detector.py's live grade_holistic() call
    assert live_env["tool_choice_type"] == "tool"
    assert isinstance(live_env["fail_open_hash"], str) and len(live_env["fail_open_hash"]) == 12


def test_ceiling_max_tokens_resolves_through_an_annassign_ceilings_dict(tmp_path):
    # CEILINGS: dict[str, OutputCeiling] = {...} is an ast.AnnAssign, not ast.Assign — the exact
    # shape that already silently blinded this gate once (RESOLVED_ROLES, see _resolved_roles_map
    # above). A reader that only walks Assign would return None here and "None == None" would
    # read as a silent, permanent pass.
    src = tmp_path / "ceilings.py"
    src.write_text(
        "class OutputCeiling:\n"
        "    def __init__(self, max_tokens, role, sized_on, evidence):\n"
        "        self.max_tokens = max_tokens\n"
        "_JUDGE = OutputCeiling(1500, 'JUDGE_MODEL', 'claude-opus-5', 'evidence')\n"
        "CEILINGS: dict = {\n"
        "    'ep_grade_judge': _JUDGE,\n"
        "}\n"
    )
    assert gate._extract_ceiling_max_tokens(src, key="ep_grade_judge") == 1500


def test_ceiling_max_tokens_resolves_replace_call_without_override():
    # "judge_divergence": _JUDGE._replace(role=..., evidence=...) — no max_tokens kwarg, so it
    # must inherit the base's value (real NamedTuple._replace semantics). Asserted against the
    # literal (1500), not against the sibling extraction — two arms resolving to the same wrong
    # answer would still pass an arm-vs-arm comparison.
    assert gate._extract_ceiling_max_tokens(gate.CEILINGS_SRC, key="judge_divergence") == 1500


def test_live_timeout_raises_when_call_site_is_renamed_away(tmp_path):
    # a refactor that drops the log_caller="ep_grade_judge" literal (renamed kwarg, call moved
    # behind a helper, etc.) must raise — a .get()-shaped reader here would recreate #547's own
    # defect class one file over.
    src = tmp_path / "ep_detector.py"
    src.write_text(
        "async def f():\n"
        "    verdict = await grade_holistic(client, payload, log_caller='some_other_bucket', "
        "timeout=25)\n"
    )
    with pytest.raises(RuntimeError):
        gate._extract_live_timeout(src, log_caller="ep_grade_judge")


def test_live_timeout_raises_when_timeout_kwarg_is_not_a_literal(tmp_path):
    src = tmp_path / "ep_detector.py"
    src.write_text(
        "async def f():\n"
        "    verdict = await grade_holistic(client, payload, log_caller='ep_grade_judge', "
        "timeout=some_variable)\n"
    )
    with pytest.raises(RuntimeError):
        gate._extract_live_timeout(src, log_caller="ep_grade_judge")


def test_fail_open_hash_stable_under_reformatting_but_sensitive_to_real_change(tmp_path):
    def _write(body_stmt: str, comment: str) -> Path:
        p = tmp_path / f"transport_{abs(hash((body_stmt, comment)))}.py"
        p.write_text(
            "async def invoke_forced_tool(client, prompt, **kw):\n"
            "    async def _call():\n"
            "        return None\n"
            "    try:\n"
            f"        {comment}\n"
            "        if is_truncated(resp):\n"
            f"            {body_stmt}\n"
            "    except Exception as e:\n"
            "        return None\n"
        )
        return p

    same_a = _write("return None", "# a comment")
    same_b = _write("return None", "# a DIFFERENT comment, same code")
    different = _write("return verdict", "# a comment")

    hash_a = gate._extract_fail_open_hash(same_a)
    hash_b = gate._extract_fail_open_hash(same_b)
    hash_c = gate._extract_fail_open_hash(different)

    assert hash_a == hash_b       # comment-only edit does not move the hash
    assert hash_a != hash_c       # a real fail-open behavior change does


# ── cross-version stability (#547 second bug: ast.dump()'s string repr is not stable across
# Python versions — the exact same commit, byte-identical judge_transport.py, hashed differently
# on a 3.14 dev machine vs a 3.12 deploy server). We can't run two interpreters in this test
# process, so these pin the PROPERTY that makes the hash version-stable instead: it must come
# from normalised source text (tokenize), never from ast.dump's representation.

_GOLDEN_TRANSPORT_SRC = (
    "async def invoke_forced_tool(client, prompt, **kw):\n"
    "    async def _call():\n"
    "        return None\n"
    "    try:\n"
    "        # a comment\n"
    "        if is_truncated(resp):\n"
    "            return None\n"
    "    except Exception as e:\n"
    "        return None\n"
)


def test_fail_open_hash_golden_value_pins_a_known_block(tmp_path):
    """A fixed source block must always hash to this exact, pre-computed value. If the
    normalisation algorithm's representation ever changes (e.g. a future edit swaps back to
    ast.dump, or changes which token fields feed the hash), this fails loudly instead of a new
    'correct' value silently getting picked up from whatever a live run happens to produce."""
    src = tmp_path / "transport.py"
    src.write_text(_GOLDEN_TRANSPORT_SRC)
    assert gate._extract_fail_open_hash(src) == "1435e794ff56"


def test_fail_open_hash_is_not_computed_via_ast_dump(tmp_path, monkeypatch):
    """Behavioural (not just textual) proof that the hash never routes through ast.dump()'s
    string representation — the exact thing that is not stable across Python versions. If
    _extract_fail_open_hash called ast.dump anywhere, this monkeypatch would raise and the
    extraction would blow up instead of returning the golden value."""
    src = tmp_path / "transport.py"
    src.write_text(_GOLDEN_TRANSPORT_SRC)

    def _boom(*a, **kw):
        raise AssertionError("ast.dump must not be called by _extract_fail_open_hash")

    monkeypatch.setattr(gate.ast, "dump", _boom)
    assert gate._extract_fail_open_hash(src) == "1435e794ff56"


def test_fail_open_hash_insensitive_to_blank_lines_and_trailing_whitespace(tmp_path):
    """Extends the reformat-insensitivity test above to the other two reformats named in #547's
    fix requirement (blank line, trailing whitespace) — not just the comment case already
    covered."""
    base = _GOLDEN_TRANSPORT_SRC
    with_blank_line = base.replace(
        "    try:\n", "    try:\n\n")  # blank line inserted right after `try:`
    with_trailing_ws = base.replace(
        "            return None\n    except",
        "            return None   \n    except")  # trailing spaces on a body line

    src_base = tmp_path / "base.py"
    src_blank = tmp_path / "blank.py"
    src_trail = tmp_path / "trail.py"
    src_base.write_text(base)
    src_blank.write_text(with_blank_line)
    src_trail.write_text(with_trailing_ws)

    h_base = gate._extract_fail_open_hash(src_base)
    assert gate._extract_fail_open_hash(src_blank) == h_base
    assert gate._extract_fail_open_hash(src_trail) == h_base


def test_fail_open_hash_sensitive_to_a_statement_moving_out_of_the_if_block(tmp_path):
    """A real logic change that a token-type-only (rather than raw-text) comparison could in
    principle miss: dedenting `return None` so it runs unconditionally instead of only inside
    `if is_truncated(resp):`. Block NESTING must still move the hash even though the exact
    indentation *characters* don't (see the reformat-insensitivity tests above)."""
    base = _GOLDEN_TRANSPORT_SRC
    dedented = base.replace(
        "        if is_truncated(resp):\n            return None\n",
        "        if is_truncated(resp):\n            pass\n        return None\n",
    )
    src_base = tmp_path / "base.py"
    src_dedented = tmp_path / "dedented.py"
    src_base.write_text(base)
    src_dedented.write_text(dedented)
    assert gate._extract_fail_open_hash(src_base) != gate._extract_fail_open_hash(src_dedented)


def test_main_survives_a_broken_envelope_extractor_without_touching_the_verdict(
        tmp_path, monkeypatch, capsys):
    """A refactor that breaks static envelope extraction must NOT crash main() into a non-zero
    exit — deploy.sh reads any non-zero exit from this script as "grade surface changed, go
    re-run the paid eval", which is exactly the coupling the operator's 2026-08-13 ruling
    forbids, arriving through the error path instead of the trigger keys. The rubric verdict
    (still matching here) must print and pass unaffected."""
    rec_path = tmp_path / "record.json"
    rec_path.write_text(json.dumps(_rec()))
    monkeypatch.setattr(gate, "RECORD", rec_path)
    monkeypatch.setattr(gate, "extract_live_keys", lambda: dict(LIVE))
    monkeypatch.setattr(gate, "extract_envelope_keys",
                        lambda: (_ for _ in ()).throw(RuntimeError("call site refactored")))
    monkeypatch.setattr(sys, "argv", ["preflight_judge_eval_gate.py"])

    rc = gate.main()
    out = capsys.readouterr().out

    assert rc == 0  # rubric/model/corpus all matched -> still OK, unaffected by the crash
    assert "UNREADABLE" in out
    assert "re-run the eval" not in out.lower()
    assert "grade surface changed" not in out.lower()


# ── `--envelope-audit-json` branch — the ONLY thing that produces the audit-row payload for
# deploy.sh to relay into mi_audit_log. Each case below is written to fail if either
# `_envelope_audit_payload` is removed/renamed OR the branch's early `return 0` behavior
# changes — that pairing is what a prior mutation check found untested (renaming the payload
# builder left all other tests green).

def test_envelope_audit_json_mode_prints_one_json_line_with_old_new_values(
        tmp_path, monkeypatch, capsys):
    """Case 1 — envelope changed: exactly one line of valid JSON, exit 0, and the VALUES (not
    just key presence) name the old and new number. Fails if `_envelope_audit_payload` is
    removed/renamed (main() would raise before printing) or stops embedding real old/new
    values in `detail`."""
    rec = _rec()
    rec["envelope"] = _env_baseline(max_tokens=500)  # baseline differs from live (1500)
    rec_path = tmp_path / "record.json"
    rec_path.write_text(json.dumps(rec))
    monkeypatch.setattr(gate, "RECORD", rec_path)
    monkeypatch.setattr(gate, "extract_envelope_keys", lambda: dict(ENV_LIVE))
    monkeypatch.setattr(sys, "argv", ["preflight_judge_eval_gate.py", "--envelope-audit-json"])

    rc = gate.main()
    out = capsys.readouterr().out

    assert rc == 0
    lines = out.splitlines()
    assert len(lines) == 1  # exactly one line — deploy.sh reads the whole captured output as one payload
    payload = json.loads(lines[0])  # must be valid JSON
    assert payload["event_type"] == "judge_envelope_changed"
    assert "500" in payload["detail"] and "1500" in payload["detail"]


def test_envelope_audit_json_mode_prints_nothing_when_envelope_unchanged(
        tmp_path, monkeypatch, capsys):
    """Case 2 — envelope unchanged: NOTHING on stdout (not even a blank line). deploy.sh keys
    off `[[ -n "$ENVELOPE_AUDIT" ]]`, so a stray line here would fire a spurious audit row on
    every deploy. Fails if the branch's `if env_changed:` guard is dropped or inverted."""
    rec = _rec()
    rec["envelope"] = _env_baseline()  # matches ENV_LIVE exactly
    rec_path = tmp_path / "record.json"
    rec_path.write_text(json.dumps(rec))
    monkeypatch.setattr(gate, "RECORD", rec_path)
    monkeypatch.setattr(gate, "extract_envelope_keys", lambda: dict(ENV_LIVE))
    monkeypatch.setattr(sys, "argv", ["preflight_judge_eval_gate.py", "--envelope-audit-json"])

    rc = gate.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert out == ""


def test_envelope_audit_json_mode_ignores_rubric_drift_prints_nothing(
        tmp_path, monkeypatch, capsys):
    """Case 3 — rubric changed but envelope unchanged: this branch never calls check()/
    extract_live_keys() and must not leak the rerun verdict into the deploy's audit-row path.
    Still exactly nothing on stdout, exit 0."""
    rec = _rec(rubric_hash="bbbb2222")  # rubric mismatch at the top level
    rec["envelope"] = _env_baseline()   # envelope section matches
    rec_path = tmp_path / "record.json"
    rec_path.write_text(json.dumps(rec))
    monkeypatch.setattr(gate, "RECORD", rec_path)
    monkeypatch.setattr(gate, "extract_envelope_keys", lambda: dict(ENV_LIVE))
    monkeypatch.setattr(sys, "argv", ["preflight_judge_eval_gate.py", "--envelope-audit-json"])

    rc = gate.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert out == ""


def test_envelope_audit_json_mode_swallows_extraction_failure_silently(monkeypatch, capsys):
    """Case 4 — extraction raises: NOTHING on stdout, exit 0 — never aborts the deploy."""
    monkeypatch.setattr(gate, "extract_envelope_keys",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(sys, "argv", ["preflight_judge_eval_gate.py", "--envelope-audit-json"])

    rc = gate.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert out == ""


def test_envelope_changed_line_prints_before_the_rubric_line(tmp_path, monkeypatch, capsys):
    """First-line-is-the-answer: when the envelope moved, that finding must be the FIRST thing
    printed, not buried after the (unrelated) rubric-unchanged line."""
    rec = _rec()
    rec["envelope"] = _env_baseline(max_tokens=500)
    rec_path = tmp_path / "record.json"
    rec_path.write_text(json.dumps(rec))
    monkeypatch.setattr(gate, "RECORD", rec_path)
    monkeypatch.setattr(gate, "extract_live_keys", lambda: dict(LIVE))
    monkeypatch.setattr(gate, "extract_envelope_keys", lambda: dict(ENV_LIVE))
    monkeypatch.setattr(sys, "argv", ["preflight_judge_eval_gate.py"])

    rc = gate.main()
    out = capsys.readouterr().out

    assert rc == 0
    first_line = out.strip().splitlines()[0]
    assert "ENVELOPE CHANGED" in first_line
    assert "unchanged" not in first_line.lower()
