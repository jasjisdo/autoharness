"""Prove that the actual Pi subprocess boundary isolates host configuration."""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BODY = '---\nname: test-workflow\ndescription: "Use when testing workflows."\ncategory: testing\n---\n# Testing\n\nRun focused tests before the full suite.\n'


@pytest.fixture
def host(tmp_path):
    cwd = tmp_path / "workspace"
    cwd.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    return {"cwd": str(cwd), "agent_dir": str(home / ".pi/agent"), "session_id": "isolation-session",
            "provider": "test", "model": "test", "home": str(home)}


def invoke(host, op, *, env=None, worker=False, **extra):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("AUTOHARNESS_")}
    clean.update(HOME=host["home"], PYTHONPATH=str(ROOT / "src"))
    clean.pop("CLAUDE_CONFIG_DIR", None)
    clean.update(env or {})
    args = [sys.executable, "-m", "autoharness.pi_bridge"] + (["--worker"] if worker else [])
    proc = subprocess.run(args, cwd=host["cwd"], env=clean, text=True, capture_output=True,
                          input=json.dumps({**host, "op": op, **extra}), timeout=30, check=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def proposal(level="project"):
    return {"action": "create", "name": "test-workflow", "body": BODY, "level": level,
            "reason": "Keep the testing workflow", "evidence": "Run focused tests before the full suite."}


def test_generic_claude_child_and_root_markers_do_not_disable_or_redirect_pi(host, tmp_path):
    env = {"AUTOHARNESS_CHILD_SESSION": "1", "AUTOHARNESS_RUN_ID": "claude-run",
           "AUTOHARNESS_PROJECT_ROOT": str(tmp_path / "foreign"), "AUTOHARNESS_DISABLE_GLOBAL": "1"}
    assert invoke(host, "session_start", env=env)["roots"]["project"] == str(Path(host["cwd"]) / ".pi")
    assert invoke(host, "stage", env=env, params=proposal("global"))["ok"]
    assert invoke(host, "settled", env=env)["verdicts"][0]["ok"]
    assert (Path(host["agent_dir"]) / "skills/test-workflow/SKILL.md").is_file()
    assert not (tmp_path / "foreign").exists()


def test_private_settings_and_child_guard_are_effective_independent_of_generic_values(host):
    env = {"AUTOHARNESS_DISABLE_GLOBAL": "0", "AUTOHARNESS_PI_DISABLE_GLOBAL": "1"}
    assert not invoke(host, "stage", env=env, params=proposal("global"))["ok"]
    assert invoke(host, "index", env={"AUTOHARNESS_PI_CHILD_SESSION": "1"})["reason"] == "recursion_guard"


def test_private_reflection_threshold_overrides_generic_setting(host, tmp_path):
    fake = tmp_path / "fake_pi.py"
    fake.write_text("import sys\nsys.stdin.read()\n")
    env = {"AUTOHARNESS_REFLECT_EVERY_N": "1", "AUTOHARNESS_PI_REFLECT_EVERY_N": "2",
           "AUTOHARNESS_PI_CONSOLIDATE_EVERY_N": "0"}
    extra = {"pi_command": [sys.executable, str(fake)]}
    invoke(host, "tool_call", env=env)
    assert not invoke(host, "settled", env=env, **extra)["triggered"]
    invoke(host, "tool_call", env=env)
    assert invoke(host, "settled", env=env, **extra)["triggered"]


def test_reflector_and_notifier_export_private_markers_only(host, tmp_path):
    capture = tmp_path / "environment.json"
    script = tmp_path / "capture.py"
    script.write_text("import json,os,sys\nfrom pathlib import Path\nsys.stdin.read()\n"
                      f"Path({str(capture)!r}).write_text(json.dumps({{k:v for k,v in os.environ.items() if k.startswith('AUTOHARNESS_')}}))\n")
    env = {"AUTOHARNESS_CHILD_SESSION": "1", "AUTOHARNESS_RUN_ID": "foreign-run",
           "AUTOHARNESS_PROJECT_ROOT": "/foreign", "AUTOHARNESS_DISABLE_GLOBAL": "1"}
    roots = {"project": str(Path(host["cwd"]) / ".pi"), "global": host["agent_dir"]}
    invoke(host, "unused", env=env, worker=True, roots=roots, run_id="private-job", role="reflector",
           window="test lesson", pi_command=[sys.executable, str(script)])
    child_env = json.loads(capture.read_text())
    assert not [k for k in child_env if k.startswith("AUTOHARNESS_") and not k.startswith("AUTOHARNESS_PI_")]
    assert child_env["AUTOHARNESS_PI_CHILD_SESSION"] == "1"
    assert child_env["AUTOHARNESS_PI_RUN_ID"] == "private-job"
    assert child_env["AUTOHARNESS_PI_PROJECT_ROOT"] == roots["project"]
    notify_env = {"AUTOHARNESS_PI_NOTIFY_CMD": shlex.join([sys.executable, str(script)])}
    assert invoke(host, "stage", env=notify_env, params=proposal())["ok"]
    invoke(host, "settled", env=notify_env)
    notified = json.loads(capture.read_text())
    assert not [k for k in notified if k.startswith("AUTOHARNESS_") and not k.startswith("AUTOHARNESS_PI_")]
    assert "create test-workflow" in notified["AUTOHARNESS_PI_NOTIFY_SUMMARY"]
    assert notified["AUTOHARNESS_PI_CHILD_SESSION"] == "1"


def test_claude_defaults_and_generic_configuration_ignore_private_pi_settings(host):
    env = {k: v for k, v in os.environ.items() if not k.startswith("AUTOHARNESS_")}
    env.update(HOME=host["home"], PYTHONPATH=str(ROOT / "src"), AUTOHARNESS_PI_DISABLE_GLOBAL="1",
               AUTOHARNESS_PI_CHILD_SESSION="1", AUTOHARNESS_PI_RUN_ID="pi-only")
    script = ('import json,os; from autoharness import config; '
              'print(json.dumps({"layers":config.active_layers(), "child":os.environ.get(config.CHILD_SESSION_ENV), '
              '"run":os.environ.get(config.RUN_ID_ENV)}))')
    proc = subprocess.run([sys.executable, "-c", script], env=env, text=True, capture_output=True, check=True)
    assert json.loads(proc.stdout) == {"layers": ["global", "project"], "child": None, "run": None}
    env["AUTOHARNESS_DISABLE_GLOBAL"] = "1"
    proc = subprocess.run([sys.executable, "-c", script], env=env, text=True, capture_output=True, check=True)
    assert json.loads(proc.stdout)["layers"] == ["project"]
