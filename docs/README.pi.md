# AutoHarness for Pi Agent

## Install

Requires Pi 1.4.0+, Node.js 22.19+, Python 3.11+, and macOS or Linux. Python uses only the
standard library. No Claude CLI, manual MCP setup or additional subagent extension is needed.
The package uses the same explicit extension/skill manifest layout as
[Superpowers](https://github.com/obra/superpowers).

```bash
pi install git:github.com/jasjisdo/autoharness
```

Restart Pi or run `/reload`. Before publication, test a checkout with
`pi install /absolute/path/to/autoharness`. The upstream `tigerless-labs/autoharness` URL only
contains the adapter after upstream merges it.

### Conda

Use an existing environment with Python 3.11+ or create the development environment:

```bash
conda env create -f environment.yml
conda activate autoharness-pi-dev
```

If it already exists, activate it instead of recreating it. Launch Pi from that shell, or set
`AUTOHARNESS_PI_PYTHON` to the environment's absolute Python executable. The value is one
executable path, not a shell command. Installation does not create a venv or modify Conda.

## Learning and recall

`/learn` asks the current model to distill this conversation through the native `stage_skill`
tool. `/skill:learn` works too. Staging queues a proposal; only the deterministic Python promoter
can validate and land it. Accepted/rejected counts are reported after settlement and retained in
run accounts. User-authored skills without AutoHarness's agent-created marker are not managed.

The extension maps Pi events as follows:

- `session_start`: lifecycle maintenance, skill index and previous-run reporting.
- `resources_discover`: expose the explicit skill roots, including the main checkout's skills
  from a linked worktree. The manifest exposes the bundled `learn` skill.
- `context`: add a request-local index without replacing the system prompt or persisted history;
  compaction summaries stay first.
- `tool_call`: advance the activity counter. Successful `read` calls on managed `SKILL.md` files
  count as loads; support-file reads count as views. Failed reads count as neither.
- `agent_settled`: count a completed request, drain this session's queue and reflect at the tool
  activity threshold. Low-level model turns are not separate requests.
- `session_shutdown`: drain proposals and flush remaining tool activity. A forced process kill
  cannot flush its in-memory branch.

New skills enter AutoHarness's file-based index immediately. Use `/reload` to refresh Pi's
native inventory and `/skill:<name>` commands. Capture uses the active branch, including ephemeral
sessions, not abandoned branches. Images, thinking and unrelated message metadata are excluded;
oversized messages are omitted, and captured text is bounded and redacted before reflection.
Raw host logs are not persistently copied. Accepted skills intentionally retain redacted evidence;
redaction is defense in depth, not a guarantee that arbitrary text contains no secrets.

## Pi / Claude isolation

| Resource | Pi project | Pi personal |
| --- | --- | --- |
| Skills | `<project>/.pi/skills/` | `<agent-dir>/skills/` |
| State and run accounts | `<project>/.pi/autoharness/` | `<agent-dir>/autoharness/` |
| Archives | `<project>/.pi/skills/.archive/` | `<agent-dir>/skills/.archive/` |

`<agent-dir>` defaults to `~/.pi/agent` and respects `PI_CODING_AGENT_DIR`. Claude retains its
independent `<project>/.claude` and `~/.claude` trees. Pi takes project identity from its session
cwd, not a shell tool's incidental `cd`; linked worktrees share the main checkout's project layer.
There is no automatic import, migration or merging between the two hosts.

Pi uses **only `AUTOHARNESS_PI_*`** configuration and process markers. Inherited generic
`AUTOHARNESS_*` settings do not configure Pi. Its owned subprocess boundaries strip those generic
variables, including Claude child guards, queue IDs and project-root overrides. Pi workers and
notifier commands export private markers and `AUTOHARNESS_PI_NOTIFY_SUMMARY` only. Claude keeps
its original generic names and behavior. The user's shell and other extensions are not globally
reconfigured. Each Pi session and reflection job has its own queue/run ID.

Before managed access, Pi checks both skill/state layers against known Claude locations: home,
project/main-worktree, existing ancestor `.claude` directories, and `CLAUDE_CONFIG_DIR`. It inspects
filesystem metadata, not Claude skill contents. Equal/nested paths, symlink aliases in either
direction (including symbol/support-file and transitive aliases), shared hardlinked files in the
managed libraries, overlapping Pi layers, and cyclic/unverifiable aliases are rejected. Unsafe
roots receive no managed writes, including error-account writes. Detached workers check before
snapshots and again after model execution, before promotion or error logging. Ordinary disjoint custom locations and the legitimate `~/.pi` project /
`~/.pi/agent` personal layout remain supported.

This is **plugin-state isolation, not an operating-system sandbox**. It does not isolate shared
project edits, deliberate user-command transfers, arbitrary agent file access or explicitly
shared source checkouts. Nor does an entry-point check defend against malicious filesystem
replacement between checking and access. Conflicting storage is refused, not automatically moved.

## Reflection restrictions and costs

Separate Pi children receive exactly `read`, `grep`, `find`, `ls` and `stage_skill`; a tool-call
guard enforces that set. Shell/write tools, automatically discovered extensions, MCP, context
files, skills, templates and themes are disabled. Only this package's staging extension is
explicitly loaded, with its private recursion guard. The Python promoter remains the sole writer;
existing locking, atomic promotion, provenance and snapshots are retained.

Children reuse the parent's selected provider/model with thinking off and ordinary personal Pi
credentials/configuration. Providers registered only by another extension or keys held only in
an SDK instance are not automatically transferable. Such configurations fail visibly rather
than enabling unrelated child code. These extra model requests may incur charges, and child
usage is not added to the parent's displayed token total. Tests use a loopback model instead.

Pi always uses the redacted bundle carrier; Claude's `AUTOHARNESS_CARRIER=fork` does not affect
it. A timeout kills the child process group. Errors are retained in run accounts and surfaced at
the next session start. Allowed read tools are not an OS filesystem sandbox.

## Configuration and migration

For settings in the [main README](../README.md#configuration), replace `AUTOHARNESS_` with
`AUTOHARNESS_PI_` for Pi, for example `AUTOHARNESS_PI_REFLECT_EVERY_N=10`,
`AUTOHARNESS_PI_DISABLE_GLOBAL=1` or `AUTOHARNESS_PI_NOTIFY_CMD`. Lifecycle thresholds, capacities,
index controls, digest settings, notifications and snapshots keep their independent defaults.
The existing curator cadence counts settled requests; reflection cadence counts tool attempts.
`.claude/settings.json` is not a Pi configuration mechanism.

The initial adapter accepted generic settings. They are now intentionally ignored without a
compatibility fallback. Rename Pi's `AUTOHARNESS_PYTHON` to `AUTOHARNESS_PI_PYTHON` and any shared
knob to its private Pi equivalent. Keep generic names only for Claude if desired. Existing data
remain in place. `AUTOHARNESS_PI_BIN` and `AUTOHARNESS_PI_TIMEOUT_S` keep their names.

| Pi-specific variable | Default | Meaning |
| --- | --- | --- |
| `AUTOHARNESS_PI_PYTHON` | `python3` | Python 3.11+ executable used by the adapter. |
| `AUTOHARNESS_PI_BIN` | Current Pi invocation, else `pi` | Optional child Pi executable path. |
| `AUTOHARNESS_PI_TIMEOUT_S` | `300` | Positive timeout in seconds per child. |

Internal `AUTOHARNESS_PI_CHILD_SESSION`, `AUTOHARNESS_PI_RUN_ID` and
`AUTOHARNESS_PI_PROJECT_ROOT` are process-owned; do not set them manually. Notifier programs
read `AUTOHARNESS_PI_NOTIFY_SUMMARY`, not Claude's `AUTOHARNESS_NOTIFY_SUMMARY`.

## Update, removal and development

```bash
pi update git:github.com/jasjisdo/autoharness
pi remove git:github.com/jasjisdo/autoharness
```

Reload/restart afterward. Removal deliberately retains learned skills and state. Back up or
archive those files separately rather than deleting roots that may contain user-installed skills.

```bash
conda activate autoharness-pi-dev
npm install --ignore-scripts --package-lock=false
npm run check
npm test
python -m pytest -m 'not live' -q
ruff check .
python tools/check_doc_links.py docs
```

Bridge, environment, path and coexistence tests cover private settings, outbound markers,
populated libraries in both directions, aliases and parallel activity. Tests use temporary homes
and data, never the production Claude instance or a real notifier. Native runtime tests launch
real Pi main/reflection processes against a loopback-only model; package tests exercise the exact
git install syntax with an isolated local transport rewrite. They skip if Pi is unavailable;
CI explicitly provides Pi and executes them. No paid model requests are required.

The advertised JSON tool schema is checked against the Python `TOOL_SCHEMA`. See the
[integration plan](superpowers/plans/2026-10-23-pi-integration.md) and
[host-isolation plan](superpowers/plans/2026-10-23-host-isolation.md) for decisions and evidence.
