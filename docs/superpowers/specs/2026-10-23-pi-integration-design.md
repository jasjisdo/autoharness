# Native Pi integration

## Intent and acceptance

Install this fork with `pi install git:github.com/jasjisdo/autoharness`, using the same explicit `package.json` resource layout as Superpowers. Installation must expose executable learning behavior, not merely a skill that refers to unavailable Claude tools. Keep the Claude integration and Python validation core intact.

## Decision and alternatives

A manifest-only port is insufficient: Claude hooks and `claude --agent` do not execute in Pi. Reimplementing the validator in TypeScript duplicates a security boundary. Use a native TypeScript extension and a small Python bridge that reuses the existing stage, promoter, lifecycle, redaction, counters, snapshots and run accounts. The user approved additive native integration and supplied the fork URL.

## Runtime

- Require Pi 1.4.0+, Node 22.19+ and Python 3.11+. The Python runtime has no third-party dependencies.
- Declare `.pi/extensions/autoharness.ts` and `skills` in the Pi manifest. No build or manual MCP configuration.
- Register a direct `stage_skill` tool and `/learn` alias. `/skill:learn` remains native.
- Use session startup for lifecycle maintenance, resource discovery for skills, request-local context for the managed index, successful `read` calls for skill-load instrumentation, and settlement for per-request counting and reflection. Flush remaining tool activity on shutdown.
- Derive the project from Pi's session cwd, never shell cwd. Store project data under `<project>/.pi` and personal data under Pi's agent directory (respect `PI_CODING_AGENT_DIR`). Pass both roots explicitly; never manage `.claude` trees. Share worktree project skills via the existing main-worktree resolver.
- Give every interactive session its own proposal queue. Never drain another session's unfinished proposals.
- Capture only the active Pi branch, including in-memory sessions. Bound and redact text before handing it to a detached worker. Do not copy the raw host transcript to disk or expose image data.
- Run reflection/curation in a separate Pi CLI process using the parent's selected provider/model, only `read`, `grep`, `find`, `ls`, and `stage_skill`. Disable automatic extensions, skills, context files, prompts, themes, MCP and project trust. Explicitly load only this extension, guarded against recursive learning. Use bundle mode; Claude's fork carrier is not portable.
- Reuse the original agent bodies with an explicit Pi tool/path mapping. The deterministic Python promoter remains the sole writer. Persist launch errors and enforce a bounded child timeout.
- Archive managed skills through the existing core; never modify user-authored skills. Skills created in a running session become native skill commands on `/reload`; the explicit index can point to their files immediately.

## Verification and delivery

Use Conda environment `autoharness-pi-dev` (Python 3.11, pytest, ruff), not venv. Test package resources, isolated roots, stage/promote/rejection, successful load accounting, per-session queues, child restrictions, launch failures, redaction, cadence and shutdown. Run all Python regressions and Node extension tests. Smoke-test actual Pi resource loading and a local git installation in isolated configuration, without real model calls or personal settings changes.

The fork contains commits absent from the original local checkout. Base work on `fork/main` without rewriting either history. Keep upstream `origin`, add `fork`, and work on `feat/pi-compatibility`. Publishing to the fork's default branch is a separate shared-branch operation; do not claim the public install command includes unpublished changes.

## Non-goals

No model-provider changes, no new subagent package requirement, no modifications to Superpowers, no migration or deletion of existing learned skills, and no automatic credential or Conda modifications during plugin installation.
