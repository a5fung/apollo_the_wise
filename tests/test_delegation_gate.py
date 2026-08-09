"""delegation_gate.py — the PreToolUse block that replaced the end-of-day-only surfaces.

The declaration (OPEN) and ledger (CLOSE) both sit at the ends of the day; the drift happens
in the middle — routing got pinned AFTER the inline work was already done, twice. This gate
intervenes at the moment the edit is attempted, because in this repo reporting surfaces drift
and only things that BLOCK hold.

The two failure modes that matter, and what pins them here:
1. **Blocking a subagent's edit** — would kill every dispatched card on its first write.
   The discriminator (agent_id/agent_type present ONLY in subagent payloads) was measured
   from real Claude Code 2.1.221 hook payloads, and these tests freeze that contract.
2. **Wedging the session** — malformed payload, corrupt routing, any internal error must
   fail OPEN (allow). The ONE deliberate exception: an absent/stale routing declaration is
   the gate's trigger, not an error.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_GATE = _ROOT / "scripts/delegation_gate.py"
sys.path.insert(0, str(_ROOT / "scripts"))

import delegation_gate  # noqa: E402
from delegation_gate import bash_write_targets, classify_gated  # noqa: E402

_REPO = str(_ROOT)


def _payload(tool: str, tool_input: dict, *, agent: bool = False) -> dict:
    """A payload with exactly the key set measured from Claude Code 2.1.221 (see gate
    docstring). `agent=True` adds the two subagent-only keys, same values as observed."""
    p = {
        "session_id": "test-session", "prompt_id": "test-prompt",
        "transcript_path": "/tmp/none.jsonl", "cwd": _REPO,
        "permission_mode": "default", "hook_event_name": "PreToolUse",
        "tool_name": tool, "tool_input": tool_input, "tool_use_id": "toolu_test",
    }
    if agent:
        p["agent_id"] = "ad561fbb43f6d2f48"
        p["agent_type"] = "general-purpose"
    return p


def _run(stdin_text: str, routing_file: Path | None = None) -> subprocess.CompletedProcess:
    """End-to-end: the gate exactly as the harness runs it — payload on stdin, verdict on
    stdout. Routing points at a per-test file so the real .apollo_routing.json never leaks in."""
    env = {k: v for k, v in os.environ.items() if k != "DELEGATION_GATE"}
    env["APOLLO_ROUTING_FILE"] = str(routing_file) if routing_file else "/nonexistent/routing.json"
    return subprocess.run(
        [sys.executable, str(_GATE)], input=stdin_text,
        capture_output=True, text=True, env=env, timeout=30)


def _verdict(proc: subprocess.CompletedProcess) -> str:
    assert proc.returncode == 0, f"gate must ALWAYS exit 0 (fail-open); stderr={proc.stderr}"
    if not proc.stdout.strip():
        return "allow"
    decision = json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]
    return decision


def _routes(tmp_path: Path, who_list: list[str], day: str | None = None) -> Path:
    day = day or delegation_gate.datetime.now(delegation_gate._PT).date().isoformat()
    f = tmp_path / "routing.json"
    f.write_text(json.dumps({
        "pt_date": day,
        "routes": [{"task": f"#{i}", "who": w, "note": ""} for i, w in enumerate(who_list)],
    }))
    return f


_IMPL_EDIT = json.dumps({"file_path": f"{_REPO}/agents/market_intelligence/db.py",
                         "old_string": "x", "new_string": "y"})


# ── the six required proofs, end-to-end ──────────────────────────────────────────────────────

class TestRequiredProofs:
    def test_denies_main_loop_impl_edit_with_no_routing(self):
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        assert _verdict(_run(json.dumps(p))) == "deny"

    def test_allows_same_edit_once_main_routing_declared(self, tmp_path):
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        rf = _routes(tmp_path, ["main"])
        assert _verdict(_run(json.dumps(p), rf)) == "allow"

    def test_allows_plan_md_unconditionally(self):
        p = _payload("Write", {"file_path": f"{_REPO}/PLAN.md", "content": "x"})
        assert _verdict(_run(json.dumps(p))) == "allow"

    def test_allows_subagent_impl_edit(self):
        # Same edit, same absent routing — the ONLY difference is the two subagent keys.
        # If this test ever fails, delegation itself is broken: every card dies on write #1.
        p = _payload("Edit", json.loads(_IMPL_EDIT), agent=True)
        assert _verdict(_run(json.dumps(p))) == "allow"

    def test_catches_bash_heredoc_write_into_scripts(self):
        cmd = "cat > scripts/sneaky_new_tool.py <<'EOF'\nprint('hi')\nEOF"
        p = _payload("Bash", {"command": cmd})
        assert _verdict(_run(json.dumps(p))) == "deny"

    def test_fails_open_on_malformed_input(self):
        for bad in ("not json at all", "", '{"tool_name": ', '[1,2,3]', '"just a string"'):
            proc = _run(bad)
            assert proc.returncode == 0
            assert proc.stdout.strip() == "", f"malformed input must allow silently: {bad!r}"


# ── discriminator contract ───────────────────────────────────────────────────────────────────

class TestSubagentDiscriminator:
    def test_agent_id_alone_allows(self):
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        p["agent_id"] = "abc123"
        assert _verdict(_run(json.dumps(p))) == "allow"

    def test_agent_type_alone_allows(self):
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        p["agent_type"] = "fork"
        assert _verdict(_run(json.dumps(p))) == "allow"

    def test_main_loop_payload_key_set_still_denies(self):
        """Freezes the measured main-loop key set: if a payload with exactly these keys is
        ever ALLOWED through an undeclared impl edit, the gate has gone silently inert."""
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        assert set(p) == {"session_id", "prompt_id", "transcript_path", "cwd",
                          "permission_mode", "hook_event_name", "tool_name",
                          "tool_input", "tool_use_id"}
        assert _verdict(_run(json.dumps(p))) == "deny"


# ── routing-declaration semantics ────────────────────────────────────────────────────────────

class TestRoutingEscape:
    def test_stale_yesterday_declaration_does_not_count(self, tmp_path):
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        rf = _routes(tmp_path, ["main"], day="2026-01-01")
        assert _verdict(_run(json.dumps(p), rf)) == "deny"

    def test_card_only_routing_does_not_unlock_main_thread(self, tmp_path):
        # Exactly the shape of a real declared day (fable + sonnet cards, no main) — declaring
        # CARD work must not license inline work; that was the whole drift.
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        rf = _routes(tmp_path, ["fable", "sonnet", "sonnet"])
        assert _verdict(_run(json.dumps(p), rf)) == "deny"

    def test_opus_counts_as_main_thread(self, tmp_path):
        # The ledger's own discrepancy check treats main and opus as the same declaration;
        # refusing "#N:opus" here would false-block a legitimately declared day.
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        rf = _routes(tmp_path, ["opus"])
        assert _verdict(_run(json.dumps(p), rf)) == "allow"

    def test_corrupt_routing_file_reads_as_undeclared(self, tmp_path):
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        rf = tmp_path / "routing.json"
        rf.write_text("{corrupt")
        assert _verdict(_run(json.dumps(p), rf)) == "deny"

    def test_env_kill_switch(self, tmp_path):
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        env = dict(os.environ)
        env["DELEGATION_GATE"] = "off"
        env["APOLLO_ROUTING_FILE"] = "/nonexistent/routing.json"
        proc = subprocess.run([sys.executable, str(_GATE)], input=json.dumps(p),
                              capture_output=True, text=True, env=env, timeout=30)
        assert proc.returncode == 0 and proc.stdout.strip() == ""


# ── deny message is actionable ───────────────────────────────────────────────────────────────

class TestDenyMessage:
    def test_names_file_and_gives_exact_command(self):
        p = _payload("Edit", json.loads(_IMPL_EDIT))
        proc = _run(json.dumps(p))
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse"
        reason = out["permissionDecisionReason"]
        assert "agents/market_intelligence/db.py" in reason
        assert 'delegation_report.py --route' in reason
        assert ":main:" in reason


# ── path classification (unit) ───────────────────────────────────────────────────────────────

class TestClassify:
    @pytest.mark.parametrize("rel", [
        "agents/market_intelligence/agent.py", "core/router.py", "channels/telegram.py",
        "shared/util.py", "scripts/check_plan.py", "infra/restore.sh",
        "tests/test_foo.py", "broker/entry_pipeline.py",
    ])
    def test_gated_dirs(self, rel):
        assert classify_gated(f"{_REPO}/{rel}", _REPO) == rel

    @pytest.mark.parametrize("path", [
        "PLAN.md", "CLAUDE.md", "CHANGELOG.md", "HANDOFF.md",
        ".apollo_open_tasks.json", ".apollo_routing.json", "data_gated_reviews.yaml",
        "docs/setups/ninem.md", ".claude/settings.json",
        "scripts/probes/_468_daily.tsv",          # probe output = analysis, not impl
        "README.md", "main.py",                   # in-repo but outside the gated dirs
    ])
    def test_never_gated_repo_paths(self, path):
        assert classify_gated(f"{_REPO}/{path}", _REPO) is None

    @pytest.mark.parametrize("path", [
        "/tmp/scratch.py", "/private/tmp/x/y.py", "/dev/null",
        "/Users/alvinfung/.claude/projects/x/memory/next-session-pickup.md",
        "/somewhere/else/agents/foo.py",          # outside the repo entirely
    ])
    def test_never_gated_outside_paths(self, path):
        assert classify_gated(path, _REPO) is None

    def test_scratchpad_dir_allowed(self):
        assert classify_gated("/private/tmp/claude-501/x/scratchpad/f.py", _REPO) is None

    def test_relative_path_resolves_against_cwd(self):
        assert classify_gated("scripts/foo.py", _REPO) == "scripts/foo.py"
        assert classify_gated("../outside.py", _REPO) is None

    def test_claude_project_dir_var_expands(self):
        assert (classify_gated("$CLAUDE_PROJECT_DIR/core/router.py", "/elsewhere")
                == "core/router.py")

    def test_non_string_and_empty_are_safe(self):
        for bad in (None, "", 42, ["x"], "-rf"):
            assert classify_gated(bad, _REPO) is None


# ── bash write-target extraction (unit) ──────────────────────────────────────────────────────

class TestBashExtraction:
    @pytest.mark.parametrize("cmd,expected_hit", [
        ("cat > scripts/x.py <<'EOF'\ncode\nEOF", "scripts/x.py"),
        ("echo hi >> agents/y.py", "agents/y.py"),
        ("pytest 2> tests/err.log", "tests/err.log"),
        ("cmd | tee core/out.py", "core/out.py"),
        ("cmd | tee -a shared/log.py", "shared/log.py"),
        ("sed -i '' 's/a/b/' channels/telegram.py", "channels/telegram.py"),
        ("cp /tmp/new.py agents/market_intelligence/new.py",
         "agents/market_intelligence/new.py"),
        ("mv draft.py core/final.py", "core/final.py"),
        ("""python3 - <<PY\nopen('scripts/gen.py', 'w').write('x')\nPY""", "scripts/gen.py"),
        ("""python3 -c "from pathlib import Path; Path('infra/x.sh').write_text('y')" """,
         "infra/x.sh"),
    ])
    def test_write_forms_are_caught(self, cmd, expected_hit):
        hits = [classify_gated(t, _REPO) for t in bash_write_targets(cmd)]
        assert expected_hit in hits

    @pytest.mark.parametrize("cmd", [
        "grep -rn 'pattern' scripts/",                       # read-only mention of a gated dir
        "python3 scripts/check_plan.py --today",             # running a script isn't writing it
        "ls agents/market_intelligence/",
        "pytest tests/ -q",
        "echo hi > /tmp/out.txt",                            # write, but not into the repo
        "cmd > /dev/null 2>&1",                              # fd plumbing, not file writes
        "git diff scripts/delegation_report.py",
        # the measured false-positive trap: READS a gated file, WRITES only to scratch —
        # attribution is per-literal-call, so the gated path (mode 'r'-implied) must not deny
        """python3 - <<PY\nsrc = open('agents/market_intelligence/db.py').read()\n"""
        """open('/tmp/analysis.txt', 'w').write(src)\nPY""",
    ])
    def test_read_only_and_out_of_repo_commands_pass(self, cmd):
        hits = [classify_gated(t, _REPO) for t in bash_write_targets(cmd)]
        assert all(h is None for h in hits), f"false positive on: {cmd!r} -> {hits}"

    def test_probe_output_write_is_not_gated(self):
        cmd = "python3 scripts/probes/_468_replay.py > scripts/probes/_468_out.tsv"
        hits = [classify_gated(t, _REPO) for t in bash_write_targets(cmd)]
        assert all(h is None for h in hits)

    def test_cp_into_bare_gated_dir_is_caught(self):
        # destination is the DIRECTORY — normpath strips the slash; must still gate
        hits = [classify_gated(t, _REPO) for t in bash_write_targets("cp /tmp/new.py scripts/")]
        assert hits == ["scripts"]

    def test_cp_into_bare_probes_dir_stays_excluded(self):
        hits = [classify_gated(t, _REPO)
                for t in bash_write_targets("cp /tmp/out.tsv scripts/probes/")]
        assert all(h is None for h in hits)


# ── other tools stay untouched ───────────────────────────────────────────────────────────────

class TestScope:
    @pytest.mark.parametrize("tool,tool_input", [
        ("Read", {"file_path": f"{_REPO}/agents/market_intelligence/db.py"}),
        ("Grep", {"pattern": "x", "path": f"{_REPO}/scripts"}),
        ("Agent", {"prompt": "edit agents/foo.py", "description": "card"}),
    ])
    def test_non_write_tools_always_allow(self, tool, tool_input):
        assert _verdict(_run(json.dumps(_payload(tool, tool_input)))) == "allow"

    def test_notebook_edit_is_gated(self):
        p = _payload("NotebookEdit", {"notebook_path": f"{_REPO}/scripts/nb.ipynb",
                                      "new_source": "x"})
        assert _verdict(_run(json.dumps(p))) == "deny"
