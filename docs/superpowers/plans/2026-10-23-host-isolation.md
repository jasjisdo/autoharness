# Pi / Claude Host Isolation Plan

> Execution: inline with test-driven development; approved goal mvl9hydw-7ihara is the authority.

## Contract and design

Pi uses only `AUTOHARNESS_PI_*`. Before importing the shared core, its CLI bridge removes inherited generic `AUTOHARNESS_*` variables from its own subprocess environment. A Pi-only configuration adapter applies private settings to core attributes and changes the core's marker names to private names; it never exports generic compatibility aliases. The Claude default configuration remains unchanged. Notification summary naming gains an explicit configurable constant with its original Claude default.

Pi-owned Python workers, reflection processes and notification commands receive private markers only. Host-owned processes and the user's shell are not globally modified. Private configuration is explicitly initialized only by the Pi CLI entry point, not by importing the core in a shared Python interpreter.

Before AutoHarness-managed access, validate both Pi layers against known Claude roots (home, project/main-worktree and optional Claude configuration directory), including symlink aliases. Compare managed skill/state subtrees rather than entire config roots: the legitimate `~/.pi` project / `~/.pi/agent` personal layout has disjoint managed subtrees. Reject cross-host and cross-layer overlaps, nested aliases, cyclic/unverifiable paths; never write a rejection log into an unsafe root. Revalidate detached workers before snapshots/promotion. This is an entry-point filesystem guard, not protection against a malicious concurrent filesystem replacement or an OS sandbox.

## Milestones

1. **Contract / reproduction:** inspect all configuration and process boundaries; reproduce inherited global-disable and child-marker coupling. Done: generic disable removes the global layer; generic child marker suppresses Pi processing. Baseline commit f79dd33; backup outside repository.
2. **Configuration / process isolation:** add `pi_runtime.py`, update bridge startup and extension process boundaries, retain Claude defaults. Tests first: generic settings ignored, private settings effective, generic markers ignored, private recursion guard effective, workers/notifiers export no generic markers.
3. **Path isolation:** add `pi_paths.py` and validate bridge and worker roots before managed access. Tests first: independent defaults/custom directories; equal/nested roots; root/symbol/support-file aliases in both directions; no mutation on refusal; main-worktree mapping.
4. **Coexistence:** seed both hosts' personal/project managed libraries; snapshot one while exercising the other's stage, promotion, use, patch, archive, lifecycle and snapshots. Run hosts concurrently and inspect actual child environments with fake processes. Exercise real Pi against the existing loopback model and local-git installation fixture.
5. **Review / delivery:** migrate docs and tests to private Pi names, run full Python/Node/type/lint/link checks, review separately, commit verified changes. Report publication separately; no credential switching or upstream push.

## Verification commands

Use Conda `autoharness-pi-dev`, not venv. Run `python -m pytest -m 'not live' -q`, `npm test`, `npm run check`, `ruff check .`, and `python tools/check_doc_links.py docs`. Native Pi package/runtime tests must execute rather than skip locally. No paid models or production Claude data are used by tests.

## Ledger

- Task 1 complete: source review and both original couplings reproduced on the clean baseline.
- Task 2 complete: private configuration/markers and filtered subprocess boundaries work; generic Claude controls remain unchanged. Environment regressions were observed failing before implementation, then passing.
- Task 3 complete: bidirectional/transitive symlink, root overlap and fail-closed worker checks passed without altering foreign data. Ordinary custom storage and home/main-worktree layouts remain valid.
- Task 4 complete: filled project/personal libraries retain byte-identical foreign state while the other host patches, counts usage, archives, maintains lifecycle and snapshots. Parallel host counters and identical symbol names remain independent; real Pi runtime/install tests passed.
- Review: separate author self-review of the final diff (no subagent tool). Findings fixed with observed RED-to-GREEN regressions: shared hardlinked files; cyclic personal-root diagnostics; directory scanning after concurrent file disappearance; missing worker layer roots that could otherwise activate the core's Claude fallback; revalidation after model execution so a changed storage alias cannot reach promotion or error logging.
- Ruling: known Claude path checks are metadata-only and fail closed when unresolvable. Arbitrary malicious filesystem replacement and deliberate non-plugin file transfers remain outside the approved sandbox boundary.
- Test environments explicitly remove inherited notifier/config controls and use temporary homes; no production Claude instance or credentials were changed.
- Delivery: local commits prepare the fork update. No push or credential/account switch is performed by this work; publication remains a separate authorized action. The final test output and goal task evidence record the exact passing counts. The independent goal auditor is the completion gate.
