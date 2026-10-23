"""Native Pi integration must exercise the existing admission and lifecycle core."""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from autoharness import config
from autoharness.lib import counters, layer, sidecar


def bridge():
    return importlib.import_module("autoharness.pi_bridge")


@pytest.fixture
def session(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    return {"cwd": str(cwd), "agent_dir": str(tmp_path / "agent"), "session_id": "pi.session-1",
            "provider": "test", "model": "test-model", "pi_command": ["pi"]}


def call(session, op, **kwargs):
    return bridge().handle({**session, "op": op, **kwargs})


def intent(name="testing-workflow"):
    return {"action": "create", "name": name, "level": "project",
            "body": f'---\nname: {name}\ndescription: "Use when testing workflows."\ncategory: testing\n---\n'
                    '# Test workflows\n\nRun the focused test before the full suite.\n',
            "reason": "Keep the demonstrated testing workflow",
            "evidence": "Run the focused test before the full suite."}


def test_pi_stage_and_settlement_land_only_in_pi_roots(session):
    start = call(session, "session_start")
    assert start["roots"] == {"project": str(Path(session["cwd"]) / ".pi"), "global": session["agent_dir"]}
    assert call(session, "stage", params=intent())["ok"]
    skill = Path(session["cwd"]) / ".pi/skills/testing-workflow/SKILL.md"
    assert not skill.exists()
    assert call(session, "settled")["verdicts"][0]["ok"]
    assert skill.is_file()
    assert not (Path(session["cwd"]) / ".claude").exists()
    assert "testing-workflow" in call(session, "index")["context"]
    assert "read" in call(session, "index")["context"]


def test_session_queues_do_not_promote_another_sessions_proposals(session):
    call(session, "stage", params=intent())
    assert call({**session, "session_id": "second"}, "settled")["verdicts"] == []
    assert not (Path(session["cwd"]) / ".pi/skills/testing-workflow").exists()
    assert call(session, "settled")["verdicts"][0]["ok"]


def test_user_authored_skills_are_not_mutated(session):
    skill = Path(session["cwd"]) / ".pi/skills/testing-workflow/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(intent()["body"])
    patch = {"action": "patch", "name": "testing-workflow", "old_string": "focused test",
             "new_string": "different test", "reason": "test", "evidence": "test"}
    assert call(session, "stage", params=patch)["ok"]
    assert not call(session, "settled")["verdicts"][0]["ok"]
    assert skill.read_text() == intent()["body"]
    assert not (skill.parent / ".sidecar.json").exists()


def test_successful_native_skill_read_counts_use_but_support_read_only_views(session):
    call(session, "stage", params=intent())
    call(session, "settled")
    path = Path(session["cwd"]) / ".pi/skills/testing-workflow/SKILL.md"
    assert call(session, "skill_read", path=str(path))["counted"]
    root = Path(session["cwd"]) / ".pi"
    assert sidecar.read(layer.PROJECT, "testing-workflow", root)["use"] == 1
    call(session, "skill_read", path=str(path.parent / "references/example.md"))
    data = sidecar.read(layer.PROJECT, "testing-workflow", root)
    assert data["use"] == 1 and data["view"] == 1
    assert not call(session, "skill_read", path=str(path.parent / "../outside/SKILL.md"))["counted"]


def test_reflection_cadence_is_tool_based_and_shutdown_flushes_tail(session, monkeypatch):
    jobs = []
    monkeypatch.setattr(bridge(), "launch_worker", lambda job: jobs.append(job))
    monkeypatch.setattr(config, "REFLECT_EVERY_N", 2)
    monkeypatch.setattr(config, "CONSOLIDATE_EVERY_N", 0)
    call(session, "tool_call")
    assert not call(session, "settled")["triggered"]
    call(session, "tool_call")
    assert call(session, "settled", entries=[])["triggered"]
    assert len(jobs) == 1
    call(session, "tool_call")
    assert call(session, "shutdown", entries=[])["triggered"]
    assert len(jobs) == 2
    assert not call(session, "shutdown", entries=[])["triggered"]
    assert counters.request_count(layer.PROJECT, Path(session["cwd"]) / ".pi") == 2


def test_capture_redacts_secrets_omits_images_and_honors_branch_cursor():
    entries = [
        {"id": "old", "type": "message", "message": {"role": "user", "content": "abandoned older context"}},
        {"id": "new", "type": "message", "message": {"role": "user", "content": [
            {"type": "text", "text": "Run tests; token ghp_" + "A" * 36},
            {"type": "image", "data": "NEVER-EXPORT-THIS-BASE64", "mimeType": "image/png"}]}},
    ]
    text = bridge().episode(entries, "old")
    assert "abandoned older context" not in text
    assert "Run tests" in text
    assert "ghp_" + "A" * 36 not in text
    assert "NEVER-EXPORT-THIS-BASE64" not in text
    assert len(bridge().episode(entries * 500, None).encode()) <= config.CAPTURE_MAX_WINDOW_BYTES
    nested = [{"type": "message", "id": "nested", "message": {"role": "assistant", "content": [
        {"type": "toolCall", "name": "inspect", "arguments": {"image": {"type": "image", "data": "NESTED-BASE64"}}}]}}]
    assert "NESTED-BASE64" not in bridge().episode(nested)


def test_pi_prior_digest_is_bounded_background_context():
    entries = [{"id": str(i), "type": "message", "message": {"role": "user", "content": f"Prior lesson {i}"}}
               for i in range(30)]
    entries.append({"id": "latest", "type": "message", "message": {"role": "user", "content": "New evidence"}})
    digest = bridge().prior_digest(entries, "29")
    assert "Prior lesson 29" in digest
    assert "Prior lesson 0\n" not in digest
    assert "New evidence" not in digest
    assert len(digest.encode()) <= config.DIGEST_MAX_BYTES


def test_child_mode_can_only_stage_and_never_runs_lifecycle(session, monkeypatch):
    monkeypatch.setenv(config.CHILD_SESSION_ENV, "1")
    assert call(session, "settled")["reason"] == "recursion_guard"
    assert not (Path(session["cwd"]) / ".pi").exists()
    monkeypatch.setenv(config.RUN_ID_ENV, "pi-child-run")
    assert call(session, "stage", params=intent())["ok"]


def test_pi_command_disables_unrelated_code_and_write_tools(session):
    argv = bridge().pi_command(session, "reflector")
    for flag in ["--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
                 "--no-context-files", "--no-mcp", "--no-session", "--no-approve"]:
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == "read,grep,find,ls,stage_skill"
    assert argv[argv.index("--provider") + 1] == "test"
    assert argv[argv.index("--model") + 1] == "test-model"
    assert argv[argv.index("-e") + 1].endswith("/.pi/extensions/autoharness.ts")
    assert not any("dangerously" in arg or arg == "claude" for arg in argv)


def test_launch_failure_is_durable_and_visible(session, monkeypatch):
    monkeypatch.setattr(config, "REFLECT_EVERY_N", 1)
    monkeypatch.setattr(config, "CONSOLIDATE_EVERY_N", 0)
    def fail(job):
        raise OSError("cannot launch")
    monkeypatch.setattr(bridge(), "launch_worker", fail)
    call(session, "tool_call")
    result = call(session, "settled", entries=[])
    assert "cannot launch" in result["error"]
    accounts = list((Path(session["cwd"]) / ".pi/autoharness/runs").glob("*.json"))
    assert any("spawn_error" in json.loads(p.read_text()) for p in accounts)


def test_worker_uses_native_pi_and_records_missing_binary(session):
    job = {**session, "roots": bridge().roots_for(session), "run_id": "test-missing-pi",
           "role": "reflector", "window": "Reusable test lesson", "pi_command": ["/missing/pi"]}
    assert bridge().run_worker(job) == []
    account = Path(session["cwd"]) / ".pi/autoharness/runs/test-missing-pi.json"
    assert json.loads(account.read_text())["spawn_error"]["returncode"] == 127


def test_global_disable_prevents_global_staging(session, monkeypatch):
    monkeypatch.setattr(config, "DISABLE_GLOBAL", True)
    assert not call(session, "stage", params={**intent(), "level": "global"})["ok"]
    call(session, "settled")
    assert not Path(session["agent_dir"]).exists()


def test_bridge_cli_is_json_only_and_reports_invalid_input(session):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    argv = [sys.executable, "-m", "autoharness.pi_bridge"]
    result = subprocess.run(argv, input=json.dumps({**session, "op": "session_start"}),
                            text=True, capture_output=True, env=env, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["roots"]["project"].endswith("/.pi")
    invalid = subprocess.run(argv, input="[]", text=True, capture_output=True, env=env, check=False)
    assert invalid.returncode != 0
    assert json.loads(invalid.stdout)["error"]


def test_native_tool_schema_matches_the_python_admission_surface():
    from autoharness.stage_skill.server import TOOL_SCHEMA
    advertised = json.loads((Path(__file__).resolve().parents[1] / ".pi/stage-skill.schema.json").read_text())
    assert advertised == TOOL_SCHEMA


def test_child_timeout_is_bounded_and_persisted(session, monkeypatch):
    monkeypatch.setenv("AUTOHARNESS_PI_TIMEOUT_S", "1")
    job = {**session, "roots": bridge().roots_for(session), "run_id": "test-timeout",
           "role": "reflector", "window": "test", "pi_command": [sys.executable, "-c", "import time; time.sleep(60)"]}
    bridge().run_worker(job)
    account = Path(session["cwd"]) / ".pi/autoharness/runs/test-timeout.json"
    error = json.loads(account.read_text())["spawn_error"]
    assert error["returncode"] == 124
    assert "timed out" in error["stderr_tail"]


def test_child_failure_is_reported_at_the_next_session_start(session):
    job = {**session, "roots": bridge().roots_for(session), "run_id": "test-error-summary",
           "role": "reflector", "window": "test", "pi_command": ["/missing/pi"]}
    bridge().run_worker(job)
    assert "127" in call(session, "session_start")["error"]


def test_worktree_uses_main_pi_skills_without_touching_claude(session, tmp_path):
    cwd = Path(session["cwd"])
    subprocess.run(["git", "init", "-q", str(cwd)], check=True)
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "--allow-empty", "-qm", "Initialize"], check=True)
    worktree = tmp_path / "worktree"
    subprocess.run(["git", "-C", str(cwd), "worktree", "add", "-qb", "test-worktree", str(worktree)], check=True)
    roots = bridge().roots_for({**session, "cwd": str(worktree)})
    assert roots["project"] == cwd / ".pi"
    assert not (cwd / ".claude").exists()


def test_parallel_tool_counts_are_not_lost(session):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: call(session, "tool_call"), range(30)))
    sid = bridge()._session_key(session)
    assert counters.session_count(sid, Path(session["cwd"]) / ".pi") == 30
