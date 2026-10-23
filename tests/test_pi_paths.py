"""Conflicting host storage must fail before any managed read or write."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_pi_environment import ROOT, invoke
from test_pi_environment import host as host


def snapshot(root):
    return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink()
            else ("file", p.read_bytes()) if p.is_file() else ("directory",)
            for p in root.rglob("*")}


def refused(host, *, worker=False, env=None, **extra):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("AUTOHARNESS_")}
    clean.update(HOME=host["home"], PYTHONPATH=str(ROOT / "src"))
    clean.pop("CLAUDE_CONFIG_DIR", None)
    clean.update(env or {})
    proc = subprocess.run([sys.executable, "-m", "autoharness.pi_bridge"] + (["--worker"] if worker else []),
                          input=json.dumps({**host, "op": "session_start", **extra}), env=clean,
                          cwd=host["cwd"], text=True, capture_output=True, timeout=20, check=False)
    assert proc.returncode != 0, proc.stdout
    assert "isolation" in json.loads(proc.stdout)["error"].lower()


@pytest.mark.parametrize("level", ["project", "global"])
def test_pi_config_root_cannot_be_a_claude_root(host, level):
    foreign = Path(host["home"]) / ".claude"
    foreign.mkdir()
    (foreign / "keep").write_text("Claude configuration remains unchanged")
    before = snapshot(foreign)
    if level == "global":
        refused({**host, "agent_dir": str(foreign)})
    else:
        (Path(host["cwd"]) / ".pi").symlink_to(foreign, target_is_directory=True)
        refused(host)
    assert snapshot(foreign) == before


@pytest.mark.parametrize("direction", ["pi-to-claude", "claude-to-pi"])
@pytest.mark.parametrize("part", ["skills", "autoharness"])
def test_cross_host_directory_aliases_are_rejected_both_directions(host, direction, part):
    pi = Path(host["cwd"]) / ".pi" / part
    claude = Path(host["cwd"]) / ".claude" / part
    target, alias = (claude, pi) if direction == "pi-to-claude" else (pi, claude)
    target.mkdir(parents=True)
    (target / "keep").write_text("existing host data")
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.symlink_to(target, target_is_directory=True)
    before = snapshot(Path(host["cwd"]))
    refused(host)
    assert snapshot(Path(host["cwd"])) == before


@pytest.mark.parametrize("reverse", [False, True])
def test_per_skill_and_transitive_external_aliases_cannot_cross_hosts(host, tmp_path, reverse):
    pi = Path(host["cwd"]) / ".pi/skills"
    claude = Path(host["cwd"]) / ".claude/skills"
    external = tmp_path / "external"
    external.mkdir()
    pi.mkdir(parents=True)
    claude.mkdir(parents=True)
    pi_target, foreign = (claude, pi) if reverse else (pi, claude)
    (pi_target / "external").symlink_to(external, target_is_directory=True)
    (external / "nested").symlink_to(foreign, target_is_directory=True)
    before = snapshot(Path(host["cwd"]))
    refused(host)
    assert snapshot(Path(host["cwd"])) == before


def test_symbol_support_file_alias_into_claude_is_rejected(host):
    claude = Path(host["cwd"]) / ".claude/skills/foreign"
    claude.mkdir(parents=True)
    ledger = claude / ".ledger.jsonl"
    ledger.write_text('untouched\n')
    pi = Path(host["cwd"]) / ".pi/skills/local"
    pi.mkdir(parents=True)
    (pi / ".ledger.jsonl").symlink_to(ledger)
    before = snapshot(Path(host["cwd"]))
    refused(host)
    assert snapshot(Path(host["cwd"])) == before


def test_pi_project_and_personal_layers_must_have_distinct_managed_subtrees(host):
    refused({**host, "agent_dir": str(Path(host["cwd"]) / ".pi")})
    refused({**host, "agent_dir": str(Path(host["cwd"]) / ".pi/skills/personal")})
    assert not (Path(host["cwd"]) / ".pi").exists()


def test_legitimate_home_and_custom_storage_layouts_are_allowed(host, tmp_path):
    home = Path(host["home"])
    result = invoke({**host, "cwd": str(home)}, "session_start")
    assert result["roots"]["project"] == str(home / ".pi")
    assert result["roots"]["global"] == str(home / ".pi/agent")
    custom = tmp_path / "separate-agent"
    assert invoke({**host, "agent_dir": str(custom)}, "session_start")["roots"]["global"] == str(custom)


def test_custom_claude_config_directory_is_protected(host, tmp_path):
    claude = tmp_path / "custom-claude"
    claude.mkdir()
    before = snapshot(claude)
    refused({**host, "agent_dir": str(claude)}, env={"CLAUDE_CONFIG_DIR": str(claude)})
    assert snapshot(claude) == before


def test_detached_worker_refuses_unsafe_roots_without_writing_an_error_account(host):
    claude = Path(host["cwd"]) / ".claude"
    claude.mkdir()
    before = snapshot(claude)
    refused(host, worker=True, roots={"project": str(claude), "global": host["agent_dir"]},
            run_id="unsafe-worker", role="reflector", window="test", pi_command=["/missing/pi"])
    assert snapshot(claude) == before


def test_worker_requires_both_layer_roots_before_any_core_fallback(host):
    claude = Path(host["home"]) / ".claude/skills"
    claude.mkdir(parents=True)
    (claude / "keep").write_text("Do not snapshot Claude through a missing Pi root")
    before = snapshot(claude.parent)
    refused(host, worker=True, roots={"project": str(Path(host["cwd"]) / ".pi")},
            run_id="missing-layer", role="curator", pi_command=["/missing/pi"])
    assert snapshot(claude.parent) == before
    assert not (Path(host["cwd"]) / ".pi/autoharness").exists()


def test_worker_rechecks_storage_after_reflection_before_promotion_or_error_logging(host, tmp_path):
    claude = Path(host["cwd"]) / ".claude/skills"
    claude.mkdir(parents=True)
    (claude / "keep").write_text("unchanged")
    before = snapshot(claude.parent)
    pi = Path(host["cwd"]) / ".pi/skills"
    fake = tmp_path / "replace_storage.py"
    fake.write_text("import sys\nfrom pathlib import Path\nsys.stdin.read()\n"
                    f"p=Path({str(pi)!r})\np.parent.mkdir(parents=True,exist_ok=True)\n"
                    f"p.symlink_to(Path({str(claude)!r}),target_is_directory=True)\n")
    refused(host, worker=True, roots={"project": str(pi.parent), "global": host["agent_dir"]},
            run_id="storage-changed", role="reflector", window="test", pi_command=[sys.executable, str(fake)])
    assert snapshot(claude.parent) == before
    assert not (pi.parent / "autoharness").exists()


def test_cyclic_symlink_is_a_clear_fail_closed_error(host):
    root = Path(host["cwd"]) / ".pi/skills"
    root.mkdir(parents=True)
    (root / "cycle").symlink_to(root, target_is_directory=True)
    refused(host)
    assert not (Path(host["cwd"]) / ".pi/autoharness").exists()


@pytest.mark.parametrize("area", ["skills", "autoharness"])
def test_shared_hardlinked_files_between_hosts_are_rejected(host, area):
    pi = Path(host["cwd"]) / ".pi" / area
    claude = Path(host["cwd"]) / ".claude" / area
    pi.mkdir(parents=True)
    claude.mkdir(parents=True)
    source = claude / "shared-ledger"
    source.write_text("unchanged")
    os.link(source, pi / "shared-ledger")
    before = snapshot(Path(host["cwd"]))
    refused(host)
    assert snapshot(Path(host["cwd"])) == before


def test_cyclic_personal_root_has_a_clear_isolation_diagnostic(host, tmp_path):
    cycle = tmp_path / "cycle"
    cycle.symlink_to(cycle, target_is_directory=True)
    refused({**host, "agent_dir": str(cycle)})


def test_disappearing_files_do_not_skip_remaining_alias_checks(host, monkeypatch):
    from contextlib import contextmanager
    from itertools import chain

    from autoharness.pi_paths import assert_isolated

    monkeypatch.setenv("HOME", host["home"])
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    pi = Path(host["cwd"]) / ".pi/skills"
    claude = Path(host["cwd"]) / ".claude/skills"
    pi.mkdir(parents=True)
    claude.mkdir(parents=True)
    (pi / "unsafe").symlink_to(claude, target_is_directory=True)
    original = os.scandir

    class Vanished:
        def is_symlink(self):
            return False

        def is_file(self, **_kwargs):
            return True

        def stat(self, **_kwargs):
            raise FileNotFoundError("concurrent atomic cleanup")

    @contextmanager
    def scandir(path):
        with original(path) as entries:
            yield chain([Vanished()], entries) if Path(path) == pi else entries

    monkeypatch.setattr(os, "scandir", scandir)
    with pytest.raises(ValueError, match="isolation"):
        assert_isolated({"project": Path(host["cwd"]) / ".pi", "global": Path(host["agent_dir"])},
                        host["cwd"], host["cwd"])
