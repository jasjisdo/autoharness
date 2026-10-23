"""Real Pi processes against a loopback-only scripted model; no paid provider calls."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def proposal(name):
    return {"action": "create", "name": name, "level": "project",
            "body": f'---\nname: {name}\ndescription: "Use when testing workflows."\ncategory: testing\n---\n'
                    '# Testing workflow\n\nRun focused tests before the full suite.\n',
            "reason": "Keep the test workflow", "evidence": "Run focused tests before the full suite."}


@pytest.mark.skipif(not shutil.which("pi"), reason="native Pi CLI is not installed")
def test_real_pi_stages_promotes_and_reflects_with_read_only_child(tmp_path):
    observed = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            observed.append(data)
            child = any("You run once after an episode" in str(m.get("content", ""))
                        for m in data["messages"] if m["role"] == "system")
            tool_seen = any(m["role"] == "tool" for m in data["messages"])
            if tool_seen:
                delta, finish = {"content": "Staged the testing lesson."}, "stop"
            else:
                name = "reflected-workflow" if child else "native-workflow"
                delta = {"tool_calls": [{"index": 0, "id": "call-stage", "type": "function", "function": {
                    "name": "stage_skill", "arguments": json.dumps(proposal(name))}}]}
                finish = "tool_calls"
            event = {"id": "test", "object": "chat.completion.chunk", "created": 1, "model": "scripted",
                     "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
            ending = {**event, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}
            body = f"data: {json.dumps(event)}\n\ndata: {json.dumps(ending)}\n\ndata: [DONE]\n\n".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "models.json").write_text(json.dumps({"providers": {"autoharness-test": {
        "baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "api": "openai-completions", "apiKey": "test",
        "models": [{"id": "scripted", "contextWindow": 100000, "maxTokens": 2000}]}}}))
    cwd = tmp_path / "workspace"
    cwd.mkdir()
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("AUTOHARNESS_")},
           "HOME": str(tmp_path / "home"), "PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1",
           "AUTOHARNESS_PI_PYTHON": sys.executable, "AUTOHARNESS_PI_REFLECT_EVERY_N": "1",
           "AUTOHARNESS_PI_CONSOLIDATE_EVERY_N": "0", "AUTOHARNESS_PI_TIMEOUT_S": "20"}
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.pop("AUTOHARNESS_PI_BIN", None)
    env.pop("AUTOHARNESS_PI_CHILD_SESSION", None)
    try:
        proc = subprocess.run(["pi", "--print", "--mode", "json", "--no-session", "--no-extensions",
                               "-e", str(ROOT / ".pi/extensions/autoharness.ts"), "--no-mcp", "--no-skills",
                               "--no-context-files", "--no-approve", "--provider", "autoharness-test",
                               "--model", "scripted", "Run focused tests before the full suite."],
                              cwd=cwd, env=env, capture_output=True, text=True, timeout=40, check=False)
        assert proc.returncode == 0, proc.stderr + proc.stdout[-5000:]
        assert (cwd / ".pi/skills/native-workflow/SKILL.md").is_file(), proc.stderr + proc.stdout[-5000:]
        deadline = time.monotonic() + 25
        reflected = cwd / ".pi/skills/reflected-workflow/SKILL.md"
        while not reflected.is_file() and time.monotonic() < deadline:
            time.sleep(0.1)
        accounts = list((cwd / ".pi/autoharness/runs").glob("*.json"))
        assert reflected.is_file(), [p.read_text() for p in accounts]
        child_requests = [d for d in observed if any("You run once after an episode" in str(m.get("content", ""))
                          for m in d["messages"] if m["role"] == "system")]
        assert child_requests
        names = {t["function"]["name"] for t in child_requests[0]["tools"]}
        assert names == {"read", "grep", "find", "ls", "stage_skill"}
        assert not (cwd / ".claude").exists()
        assert "stage_skill" in {t["function"]["name"] for t in observed[0]["tools"]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
