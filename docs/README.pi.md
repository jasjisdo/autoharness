# AutoHarness for Pi Agent

## Requirements and installation

This fork is a native Pi package, using the same explicit `package.json` extension/skill manifest
layout as [Superpowers](https://github.com/obra/superpowers). Its executable adapter also ports
AutoHarness's learning pipeline; a manifest alone cannot run Claude hooks in Pi.

Requirements: Pi 1.4.0+, Node.js 22.19+, Python 3.11+ and macOS or Linux. Python uses only the
standard library. Pi supplies the extension host; installing this package does not install Claude,
a Python environment, an MCP server, or a subagent package.

```bash
pi install git:github.com/jasjisdo/autoharness
```

Restart Pi or run `/reload`. For a checkout before publication, test locally with
`pi install /absolute/path/to/autoharness`. The upstream `tigerless-labs/autoharness` URL only
provides this adapter after upstream merges it.

### Conda

Use an existing environment with Python 3.11+ or create one for development from the repository:

```bash
conda env create -f environment.yml
conda activate autoharness-pi-dev
```

If the environment already exists, activate it instead of recreating it. Launch Pi from that
shell so `python3` resolves to Conda. Alternatively, set `AUTOHARNESS_PYTHON` to the environment's
absolute Python executable; AutoHarness treats it as one executable path, not a shell command.
There is no `venv` setup and Pi installation does not modify Conda environments.

## What runs

- `session_start`: maintain the managed library and prepare the skill index and prior-run report.
- `resources_discover`: surface the explicit Pi skill roots, including the main checkout's skills
  from a linked worktree. The package manifest exposes the bundled `learn` skill.
- `context`: add a request-local managed index without replacing Pi's system prompt or changing
  the persisted conversation. Compaction summaries stay before the index.
- `tool_call`: advance the tool-activity counter. A successful `read` of a managed `SKILL.md`
  counts as a load; reading support files counts as a view. Failed reads count as neither.
- `agent_settled`: count a completed request, drain this session's interactive proposal queue and
  reflect when the activity threshold is reached. Pi's low-level model turns are not requests.
- `session_shutdown`: drain remaining interactive proposals and flush any remaining tool activity.
  A process killed without orderly shutdown cannot flush its in-memory branch.

`/learn` asks the current model to distill this conversation through `stage_skill`. The native
`/skill:learn` command works too. Both require the extension/tool to be enabled. Staging queues a
proposal; it does not bypass validation or claim a skill has landed. Accepted and rejected counts
are reported after settlement, with durable run accounts on disk.

New skills appear immediately in AutoHarness's file-based recall index. Use `/reload` to refresh
Pi's native skill inventory and `/skill:<name>` commands. User-authored skills are never managed
unless they already carry AutoHarness's existing agent-created marker.

## Storage and isolation

| Resource | Project | Personal |
| --- | --- | --- |
| Skills | `<project>/.pi/skills/` | `<agent-dir>/skills/` |
| State and run accounts | `<project>/.pi/autoharness/` | `<agent-dir>/autoharness/` |
| Archived skills | `<project>/.pi/skills/.archive/` | `<agent-dir>/skills/.archive/` |

`<agent-dir>` defaults to `~/.pi/agent` and respects `PI_CODING_AGENT_DIR`. Project identity comes
from Pi's session cwd, not an incidental `cd` in the shell tool. Linked worktrees share the main
checkout's project layer, matching AutoHarness's existing worktree policy. Pi and Claude trees
are independent; installing or removing this adapter does not migrate either library.

Each Pi session has its own interactive proposal queue. Reflection jobs have unique run IDs.
Existing core locks, atomic promotion, provenance ledgers, snapshots and managed-only guards
remain authoritative. The extension serializes its bridge operations so parallel tool events do
not overwrite in-memory state. File counters are protected across processes.

The supplied active Pi branch is captured, including ephemeral sessions. Abandoned branches,
image blocks, thinking blocks and unrelated message metadata are excluded. Text is byte-bounded
and redacted before a worker receives it. Raw host logs are not copied to another persistent file.
As in upstream AutoHarness, redacted evidence is intentionally retained with accepted skills.
Redaction is defense in depth, not a guarantee that arbitrary session text contains no secrets.

## Reflection safety and model costs

Reflection and curation run in separate Pi processes. Each child receives only `read`, `grep`,
`find`, `ls` and `stage_skill`; a tool-call guard enforces that allowlist. Shell and direct-write
tools, automatically discovered extensions, MCP, context files, skills, templates and themes are
disabled. Only this package's staging extension is explicitly loaded, with recursive learning off.
The Python promoter remains the sole skill-tree writer.

These are capability restrictions, not an OS filesystem sandbox: the child can read files with
its allowed tools and the process has the user's OS permissions. Review learned skills before
using them in sensitive environments. Do not rely on unattended learning as a secrets boundary.

Children reuse the parent's selected provider/model with thinking off. They use Pi's ordinary
personal credentials and provider configuration; a provider registered only by another extension,
or a key supplied only to an SDK instance, is not automatically transferable. Configure an
ordinary Pi provider before unattended use. Reflection makes additional model requests and can
incur charges. Child usage is not added to the parent's displayed token total.

Pi always uses the redacted **bundle** carrier; `AUTOHARNESS_CARRIER=fork` remains Claude-specific.
A child is killed, including its process group, after the timeout. Run accounts record nonzero
exits and timeouts; the next session startup also surfaces the last worker error.

## Configuration

Set environment variables in the shell that launches Pi (including an activated Conda shell).
The shared `AUTOHARNESS_*` knobs in the [main README](../README.md#configuration) retain their
Python-core behavior, including project-only placement, index suppression, lifecycle thresholds,
notifications and snapshots. `.claude/settings.json` is not a Pi configuration mechanism.

Pi-specific variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUTOHARNESS_PYTHON` | `python3` | Python 3.11+ executable, also used in child sessions. |
| `AUTOHARNESS_PI_BIN` | Current Pi invocation, else `pi` | Optional Pi executable path for child processes. |
| `AUTOHARNESS_PI_TIMEOUT_S` | `300` | Positive timeout in seconds per reflection or curation child. |

Reflection cadence counts main-session tool attempts, matching the original PreToolUse behavior.
The shared curator cadence currently counts settled requests, matching the existing Python
dispatcher. Missing Python or launch failures are reported without crashing normal Pi work.
Malformed or rejected proposals return an error result to the model so it can correct them.

## Update and remove

```bash
pi update git:github.com/jasjisdo/autoharness
pi remove git:github.com/jasjisdo/autoharness
```

Restart Pi or `/reload` after updating. Removal stops future execution after reload; it deliberately
retains learned skills and state. Archive or back up those files separately rather than deleting
entire skill roots, which may contain skills you created or installed yourself.

## Development and verification

```bash
conda activate autoharness-pi-dev
npm install --ignore-scripts --package-lock=false
npm run check
npm test
python -m pytest -m 'not live' -q
ruff check .
python tools/check_doc_links.py docs
```

`tests/test_pi_bridge.py` exercises the real Python core with isolated roots. Node tests exercise
the native extension and its process boundary. `tests/test_pi_runtime.py` launches real Pi main
and reflection processes against a loopback-only scripted model, checking promotion and the
child's actual tool declarations. It skips when the Pi executable is unavailable; CI's Pi job
provides the executable and runs this test explicitly. No paid model calls are needed.

The advertised staging JSON schema is checked against the Python tool's `TOOL_SCHEMA`; update
the snapshot when that source changes. Review [the design](superpowers/specs/2026-10-23-pi-integration-design.md)
and [implementation record](superpowers/plans/2026-10-23-pi-integration.md) for integration decisions.
