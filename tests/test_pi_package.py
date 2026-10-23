"""Exercise the exact public install syntax using a local git transport rewrite."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "git:github.com/jasjisdo/autoharness"


@pytest.mark.skipif(not shutil.which("pi"), reason="native Pi CLI is not installed")
def test_git_install_discovers_learn_command_and_skill_without_global_changes(tmp_path):
    snapshot = tmp_path / "source"
    snapshot.mkdir()
    files = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                                    cwd=ROOT).decode().split("\0")
    for filename in filter(None, files):
        target = snapshot / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / filename, target)
    subprocess.run(["git", "init", "-q", str(snapshot)], check=True)
    subprocess.run(["git", "-C", str(snapshot), "add", "."], check=True)
    subprocess.run(["git", "-C", str(snapshot), "-c", "user.name=Package test", "-c", "user.email=test@example.com",
                    "commit", "-qm", "Package fixture"], check=True)
    agent = tmp_path / "agent"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = {**os.environ, "PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1",
           "AUTOHARNESS_PYTHON": sys.executable}
    index = int(env.get("GIT_CONFIG_COUNT", "0"))
    env.update(GIT_CONFIG_COUNT=str(index + 1))
    env[f"GIT_CONFIG_KEY_{index}"] = f"url.{snapshot.as_uri()}.insteadOf"
    env[f"GIT_CONFIG_VALUE_{index}"] = "https://github.com/jasjisdo/autoharness"
    installed = subprocess.run(["pi", "install", SOURCE], env=env, cwd=workspace,
                               capture_output=True, text=True, timeout=90, check=False)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    clone = agent / "git/github.com/jasjisdo/autoharness"
    assert (clone / "package.json").is_file()
    assert (clone / ".git").exists()
    assert SOURCE in (agent / "settings.json").read_text()
    proc = subprocess.run(["pi", "--mode", "rpc", "--no-session", "--no-mcp", "--no-context-files",
                           "--no-approve", "--offline"],
                          input='{"id":"commands","type":"get_commands"}\n', cwd=workspace,
                          env=env, text=True, capture_output=True, timeout=40, check=False)
    assert proc.returncode == 0, proc.stderr
    records = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    response = next(record for record in records if record.get("id") == "commands")
    assert response["success"], response
    commands = {command["name"]: command for command in response["data"]["commands"]}
    assert commands["learn"]["source"] == "extension"
    assert commands["skill:learn"]["source"] == "skill"
    assert commands["learn"]["sourceInfo"]["origin"] == "package"
    assert commands["learn"]["sourceInfo"]["source"] == SOURCE
    assert "failed" not in proc.stderr.lower(), proc.stderr
