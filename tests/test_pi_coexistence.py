"""Exercise filled Pi/Claude libraries independently and in parallel, without live hosts."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from test_pi_environment import BODY, ROOT, invoke, proposal
from test_pi_environment import host as host
from test_pi_paths import snapshot

CLAUDE_DRIVER = '''
import json,subprocess,sys
from pathlib import Path
from autoharness.hook import dispatch,spawn
from autoharness.stage_skill.server import stage
r=json.load(sys.stdin)
roots={"project":Path(r["cwd"])/".claude", "global":Path.home()/".claude"}
op=r["op"]
event={"session_id":r["session_id"],"cwd":r["cwd"]}
if op=="stage":
    result=stage(r["params"],run_id="interactive",root=roots["project"])
elif op=="settled":
    result=dispatch.dispatch({**event,"hook_event_name":"Stop"},roots=roots)
elif op=="session_start":
    result=dispatch.dispatch({**event,"hook_event_name":"SessionStart"},roots=roots)
elif op=="skill_read":
    result=dispatch.dispatch({**event,"hook_event_name":"PreToolUse","tool_name":"Skill",
                              "tool_input":{"skill":r["name"]}},roots=roots)
elif op=="tool_call":
    result=dispatch.dispatch({**event,"hook_event_name":"PreToolUse","tool_name":"Bash"},roots=roots)
elif op=="curate":
    result=spawn.run_curator("claude-curate",roots=roots,
          spawn_fn=lambda *args:subprocess.CompletedProcess(["fake-model"],0))
print(json.dumps(result))
'''


def claude(host, op, *, env=None, **extra):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("AUTOHARNESS_")}
    clean.update(HOME=host["home"], PYTHONPATH=str(ROOT / "src"), AUTOHARNESS_REFLECT_EVERY_N="99999",
                 AUTOHARNESS_CONSOLIDATE_EVERY_N="0")
    clean.update(env or {})
    proc = subprocess.run([sys.executable, "-c", CLAUDE_DRIVER], cwd=host["cwd"], env=clean,
                          input=json.dumps({**host, "op": op, **extra}), capture_output=True,
                          text=True, timeout=30, check=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return json.loads(proc.stdout)


def pi(host, op, *, env=None, **extra):
    return invoke(host, op, env={"AUTOHARNESS_PI_REFLECT_EVERY_N": "99999",
                                "AUTOHARNESS_PI_CONSOLIDATE_EVERY_N": "0", **(env or {})}, **extra)


def roots(host, which):
    if which == "pi":
        return {"project": Path(host["cwd"]) / ".pi", "global": Path(host["agent_dir"])}
    return {"project": Path(host["cwd"]) / ".claude", "global": Path(host["home"]) / ".claude"}


def named(name, level="project"):
    return {**proposal(level), "name": name, "body": BODY.replace("test-workflow", name)}


def seed(host, which):
    action = pi if which == "pi" else claude
    for name, level in (("project-workflow", "project"), ("global-workflow", "global"), ("unused-workflow", "project")):
        assert action(host, "stage", params=named(name, level))["ok"]
        action(host, "settled")
    for root in roots(host, which).values():
        manual = root / "skills/manual/SKILL.md"
        manual.parent.mkdir(parents=True)
        manual.write_text(BODY.replace("test-workflow", "manual"))


def observe(host, which):
    return {level: snapshot(root) for level, root in roots(host, which).items()}


@pytest.mark.parametrize("active", ["pi", "claude"])
def test_filled_libraries_stay_unchanged_while_other_host_changes_maintains_and_snapshots(host, tmp_path, active):
    seed(host, "pi")
    seed(host, "claude")
    other = "claude" if active == "pi" else "pi"
    before = observe(host, other)
    action = pi if active == "pi" else claude
    own = roots(host, active)
    inherited = {"AUTOHARNESS_DISABLE_GLOBAL": "1", "AUTOHARNESS_CHILD_SESSION": "1"} if active == "pi" else {
        "AUTOHARNESS_PI_DISABLE_GLOBAL": "1", "AUTOHARNESS_PI_CHILD_SESSION": "1"}
    if active == "pi":
        assert action(host, "skill_read", env=inherited, path=str(own["project"] / "skills/project-workflow/SKILL.md"))["counted"]
    else:
        assert action(host, "skill_read", env=inherited, name="project-workflow")["result"]["counted"]
    marker = f"{active}-specific workflow"
    patch = {"action": "patch", "name": "project-workflow", "old_string": "Run focused tests",
             "new_string": f"Use the {marker}; run focused tests", "reason": "Keep host-specific lesson",
             "evidence": "Run focused tests before the full suite."}
    assert action(host, "stage", env=inherited, params=patch)["ok"]
    action(host, "settled", env=inherited)
    assert marker in (own["project"] / "skills/project-workflow/SKILL.md").read_text()
    assert action(host, "stage", params=named("retired-workflow"))["ok"]
    action(host, "settled")
    retire = {"action": "delete", "name": "retired-workflow", "reason": "Retire a host-specific skill",
              "evidence": "The workflow was retired."}
    assert action(host, "stage", params=retire)["ok"]
    action(host, "settled")
    assert (own["project"] / "skills/.archive/retired-workflow/SKILL.md").is_file()
    if active == "pi":
        fake = tmp_path / "fake_pi.py"
        fake.write_text("import sys\nsys.stdin.read()\n")
        invoke(host, "unused", worker=True, roots={k: str(v) for k, v in own.items()},
               role="curator", run_id="pi-curate", pi_command=[sys.executable, str(fake)])
    else:
        action(host, "curate")
    assert list((own["project"] / "autoharness/snapshots").glob("*.tar.gz"))
    prefix = "AUTOHARNESS_PI_" if active == "pi" else "AUTOHARNESS_"
    action(host, "session_start", env={prefix + "MATURITY_PROJECT": "0", prefix + "MATURITY_GLOBAL": "0"})
    assert (own["project"] / "skills/.archive/unused-workflow/SKILL.md").is_file()
    assert (own["project"] / "skills/project-workflow/SKILL.md").is_file()
    assert (own["project"] / "skills/manual/SKILL.md").is_file()
    assert observe(host, other) == before


def test_parallel_hosts_keep_their_own_counters_queues_and_identical_symbol_names(host):
    seed(host, "pi")
    seed(host, "claude")
    starts = {which: int((roots(host, which)["project"] / "autoharness/requests").read_text())
              for which in ("pi", "claude")}
    def work(which):
        action = pi if which == "pi" else claude
        for _ in range(8):
            action(host, "tool_call")
            action(host, "settled")
        patch = {"action": "patch", "name": "project-workflow", "old_string": "Run focused tests",
                 "new_string": f"Use {which} independently; run focused tests", "reason": "Keep this host's workflow",
                 "evidence": "Run focused tests before the full suite."}
        assert action(host, "stage", params=patch)["ok"]
        action(host, "settled")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(work, ("pi", "claude")))
    for which in ("pi", "claude"):
        root = roots(host, which)["project"]
        assert int((root / "autoharness/requests").read_text()) == starts[which] + 9
        text = (root / "skills/project-workflow/SKILL.md").read_text()
        assert f"Use {which} independently" in text
        assert f"Use {'claude' if which == 'pi' else 'pi'} independently" not in text
        assert json.loads((root / "skills/project-workflow/.sidecar.json").read_text())["patch"] == 1
