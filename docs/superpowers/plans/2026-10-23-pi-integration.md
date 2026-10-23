# Pi Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this fork a fully functional native Pi package installable with `pi install git:github.com/jasjisdo/autoharness`.

**Architecture:** A TypeScript extension adapts Pi events and tools to a Python JSON bridge. The bridge passes explicit Pi roots into the existing validator, promoter and lifecycle; detached reflection uses a restricted Pi CLI process rather than Claude.

**Tech Stack:** Pi 1.4+, Node 22.19+, TypeScript, Python 3.11 standard library; Conda `autoharness-pi-dev` for pytest/ruff.

**Spec:** `docs/superpowers/specs/2026-10-23-pi-integration-design.md`

## Global Constraints

- Preserve Claude behavior and user-authored skills; never manage `.claude` through Pi.
- Use Conda, not venv. No new Python runtime dependencies.
- Keep the fork's history. Upstream remote remains unchanged.
- No paid model request is needed for deterministic integration tests.
- Back up existing files before edits. Public installation requires publication.

## Review Focus

- Parallel Pi tools and multiple sessions must not mix proposal queues or lose counters.
- Active-branch capture must exclude abandoned history and image/base64 payloads.
- Missing Python/CLI, child errors and timeouts must be visible, without breaking the user's session.
- Reflection must have no shell, write, unrelated extension or MCP capability.
- Dynamic skill recall and successful skill reads must work in worktrees and ephemeral sessions.

### Task 1: Python Pi bridge and reflection worker

**Files:** Create `src/autoharness/pi_bridge.py`, `tests/test_pi_bridge.py`.

**Interfaces:** JSON stdin/stdout `handle(request)` with `session_start`, `index`, `tool_call`, `skill_read`, `stage`, `settled`, `shutdown`; internal `run_worker(job)` and `pi_command(job, role)`.

- [x] Write failing integration tests for explicit roots, staging/promoting, manual-skill protection, successful skill use, per-session queues, reflection cadence, worker errors, redaction and restricted child arguments.
- [x] Run `conda run -n autoharness-pi-dev python -m pytest tests/test_pi_bridge.py -q`; verify failure because the bridge is missing.
- [x] Implement the bridge using the existing core and explicit project/global roots; spawn detached workers with redacted bounded payloads on stdin.
- [x] Run focused tests, then full Python tests and ruff; verify green.

### Task 2: Native Pi extension and package

**Files:** Create `package.json`, `.pi/extensions/autoharness.ts`, `.pi/stage-skill.schema.json`, `tests/pi/test-pi-extension.mjs`.

**Interfaces:** The extension invokes Task 1's JSON bridge, registers `stage_skill`, `/learn`, and Pi events. A checked JSON schema is generated from the Python tool's single-source schema.

- [x] Write failing Node tests for manifest/resource loading, native tools/commands, contextual index, lifecycle mapping, active-branch serialization, error isolation and child restrictions.
- [x] Run `node --test tests/pi/*.mjs`; verify missing package/extension failure.
- [x] Implement native extension with async subprocess calls and ordered bridge operations; reuse tool schema and bundled learn skill.
- [x] Run Node tests, Python tests and actual Pi RPC discovery without paid model calls; verify registered resources, commands and tools.

### Task 3: Documentation, CI and install verification

**Files:** Modify `README.md`, `.github/workflows/ci.yml`; create `docs/README.pi.md`, `environment.yml`, `AGENTS.md` and verification notes.

- [x] Document exact fork installation, Conda setup, storage isolation, `/learn`, reload behavior, settings, restrictions, errors and uninstall semantics.
- [x] Add Node tests to CI without changing existing Python checks.
- [x] Perform an actual local-git package installation using isolated Pi configuration; inspect loaded resources with real Pi RPC.
- [x] Run full test suites, lint and documentation link check; review the diff separately.
- [x] Commit verified changes (`d04e6bb`, native Pi integration).
- [ ] Publish to the fork after obtaining push permission; the installed GitHub account currently has pull-only access (HTTP 403 on push dry-run).

## Execution ledger

- Baseline: fork `c0aef3f`; 686 tests passed, 1 live test deselected, Python 3.11.17 in Conda.
- Backup: `/Volumes/T7_Shield_4TB/ai/pi/backups/autoharness-before-pi-20261023-1842.tar.gz`.
- Ruling: execute inline because no subagent tool is available. Work in the user-specified checkout on a feature branch, not a worktree; original `main` is untouched.
- Ruling: use current documented Node floor 22.19+, correcting the design's provisional 22.6+ value.
- Pre-flight: Task 2 consumes Task 1's JSON operations; Task 3 consumes the manifest, scripts and storage paths. No conflicting signatures identified.
- Task 1: complete. Python bridge tests and regression suite passed in Conda. Schema parity, parallel counters, distinct session queues, worktree roots, timeout and error reporting are covered.
- Task 2: complete. TypeScript checking and seven Node tests passed. Real Pi main/child processes successfully promoted skills against a loopback-only scripted model, with exactly the read-only/staging child tool set.
- Task 3: local verification complete. Exact git install syntax passed using a temporary local transport rewrite and isolated Pi settings; package discovery exposed both `/learn` and `/skill:learn`.
- Final review: self-review (no subagent tool). Review fixes: exclude unrelated message metadata and nested image payloads; avoid invoking arbitrary embedding scripts as Pi; surface detached-worker errors at the next session start. Each behavior has regression coverage observed failing before its fix.
- Ruling: workers use the parent's ordinary Pi provider configuration, not private in-memory SDK credentials or unrelated provider extensions. Those nontransferable configurations fail visibly instead of enabling extra child code; this limitation is documented.
- Verification: 706 Python tests passed, one existing paid/live test deselected; seven Node tests passed; TypeScript, ruff and documentation links passed. Remote CI execution is not claimed.
- Publication: GitHub API reports `push: false`; `git push --dry-run fork HEAD:main` returns HTTP 403. No remote branch was changed. Goal execution must pause for authentication by an account with write permission before publishing; the public fork command is not yet claimed to install these changes.
