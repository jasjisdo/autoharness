import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, mkdir, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const root = resolve(import.meta.dirname, '../..');
const extension = resolve(root, '.pi/extensions/autoharness.ts');

async function harness(environment = {}) {
  const python = process.env.AUTOHARNESS_PI_PYTHON;
  for (const key of Object.keys(process.env)) if (key.startsWith('AUTOHARNESS_')) delete process.env[key];
  if (python) process.env.AUTOHARNESS_PI_PYTHON = python;
  delete process.env.CLAUDE_CONFIG_DIR;
  Object.assign(process.env, environment);
  const cwd = await realpath(await mkdtemp(resolve(tmpdir(), 'autoharness-pi-test-')));
  process.env.HOME = resolve(cwd, 'home');
  const agentDir = resolve(cwd, 'agent');
  await mkdir(resolve(agentDir, 'skills'), { recursive: true });
  const fakePi = resolve(cwd, 'fake-pi');
  await writeFile(fakePi, '#!/bin/sh\nexit 0\n', { mode: 0o700 });
  process.env.PI_CODING_AGENT_DIR = agentDir;
  process.env.AUTOHARNESS_PI_BIN = fakePi;
  const handlers = new Map(), tools = new Map(), commands = new Map(), notices = [], sent = [];
  const pi = {
    on(name, handler) { handlers.set(name, handler); },
    registerTool(tool) { tools.set(tool.name, tool); },
    registerCommand(name, command) { commands.set(name, command); },
    sendUserMessage(text) { sent.push(text); },
    appendEntry() {},
  };
  const mod = await import(`${pathToFileURL(extension).href}?instance=${Math.random()}`);
  mod.default(pi);
  const ctx = { cwd, hasUI: true, ui: { notify(text) { notices.push(text); } },
    model: { provider: 'test', id: 'test' },
    sessionManager: { getSessionId: () => 'test-session', getBranch: () => [] } };
  return { cwd, agentDir, handlers, tools, commands, notices, sent, ctx };
}

const proposal = {
  action: 'create', name: 'test-workflow', level: 'project',
  body: '---\nname: test-workflow\ndescription: "Use when testing workflows."\ncategory: testing\n---\n# Testing\n\nRun focused tests before the full suite.\n',
  reason: 'Retain the testing workflow', evidence: 'Run focused tests before the full suite.',
};

test('manifest exposes the extension and bundled skills like Superpowers', async () => {
  const pkg = JSON.parse(await readFile(resolve(root, 'package.json'), 'utf8'));
  assert.ok(pkg.keywords.includes('pi-package'));
  assert.deepEqual(pkg.pi.extensions, ['./.pi/extensions/autoharness.ts']);
  assert.deepEqual(pkg.pi.skills, ['./skills']);
  for (const path of [...pkg.pi.extensions, './skills/learn/SKILL.md']) {
    assert.ok((await readFile(resolve(root, path), 'utf8')).length);
  }
  assert.equal(pkg.repository.url, 'https://github.com/jasjisdo/autoharness.git');
});

test('native stage tool lands through Python only after settlement and injects recall', async () => {
  const h = await harness();
  await h.handlers.get('session_start')({}, h.ctx);
  const staged = await h.tools.get('stage_skill').execute('call', proposal, undefined, undefined, h.ctx);
  assert.equal(staged.isError, false);
  await assert.rejects(readFile(resolve(h.cwd, '.pi/skills/test-workflow/SKILL.md')));
  await h.handlers.get('agent_settled')({}, h.ctx);
  assert.match(await readFile(resolve(h.cwd, '.pi/skills/test-workflow/SKILL.md'), 'utf8'), /Run focused/);
  const user = { role: 'user', content: 'Do the work', timestamp: 1 };
  const context = await h.handlers.get('context')({ messages: [user] }, h.ctx);
  assert.equal(context.messages.at(-1), user);
  assert.match(context.messages[0].content[0].text, /test-workflow/);
  assert.equal(await h.handlers.get('context')({ messages: context.messages }, h.ctx), undefined);
  const resources = await h.handlers.get('resources_discover')({}, h.ctx);
  assert.ok(resources.skillPaths.includes(resolve(h.cwd, '.pi/skills')));
  assert.ok(resources.skillPaths.includes(resolve(h.agentDir, 'skills')));
});

test('/learn sends the bundled skill instructions without inventing a Skill tool', async () => {
  const h = await harness();
  await h.commands.get('learn').handler('', h.ctx);
  assert.match(h.sent[0], /stage_skill/);
  assert.match(h.sent[0], /distill/);
});

test('successful reads of managed SKILL.md count use; failed reads do not', async () => {
  const h = await harness();
  await h.handlers.get('session_start')({}, h.ctx);
  await h.tools.get('stage_skill').execute('call', proposal, undefined, undefined, h.ctx);
  await h.handlers.get('agent_settled')({}, h.ctx);
  const event = { toolName: 'read', input: { path: '.pi/skills/test-workflow/SKILL.md' }, isError: true };
  await h.handlers.get('tool_result')(event, h.ctx);
  const sidecar = resolve(h.cwd, '.pi/skills/test-workflow/.sidecar.json');
  assert.equal(JSON.parse(await readFile(sidecar, 'utf8')).use, 0);
  await h.handlers.get('tool_result')({ ...event, isError: false }, h.ctx);
  assert.equal(JSON.parse(await readFile(sidecar, 'utf8')).use, 1);
});

test('missing Python produces visible diagnostics but does not crash session events', async () => {
  const h = await harness();
  const previousPython = process.env.AUTOHARNESS_PI_PYTHON;
  process.env.AUTOHARNESS_PI_PYTHON = '/does/not/exist/python';
  try {
    await h.handlers.get('session_start')({}, h.ctx);
    assert.ok(h.notices.some(text => /autoharness/i.test(text)));
    const result = await h.tools.get('stage_skill').execute('call', proposal, undefined, undefined, h.ctx);
    assert.equal(result.isError, true);
  } finally {
    if (previousPython) process.env.AUTOHARNESS_PI_PYTHON = previousPython;
    else delete process.env.AUTOHARNESS_PI_PYTHON;
  }
});

test('active-branch capture excludes images, private metadata and abandoned branches', async () => {
  const h = await harness();
  const previousPython = process.env.AUTOHARNESS_PI_PYTHON;
  const fakePython = resolve(h.cwd, 'capture-bridge');
  const capture = resolve(h.cwd, 'bridge-input.json');
  await writeFile(fakePython, '#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\nx=json.load(sys.stdin)\nPath(' + JSON.stringify(capture) + ').write_text(json.dumps(x))\nprint("{}")\n', { mode: 0o700 });
  process.env.AUTOHARNESS_PI_PYTHON = fakePython;
  const previousPi = process.env.AUTOHARNESS_PI_BIN;
  delete process.env.AUTOHARNESS_PI_BIN;
  h.ctx.sessionManager.getBranch = () => [
    { type: 'message', id: 'active', message: { role: 'user', content: [
      { type: 'text', text: 'Current branch lesson' },
      { type: 'image', data: 'PRIVATE-IMAGE', mimeType: 'image/png' },
    ], details: { privateData: 'PRIVATE-METADATA' } } },
  ];
  try {
    await h.handlers.get('agent_settled')({}, h.ctx);
    const payload = await readFile(capture, 'utf8');
    assert.match(payload, /Current branch lesson/);
    assert.doesNotMatch(payload, /PRIVATE-IMAGE|PRIVATE-METADATA/);
    assert.deepEqual(JSON.parse(payload).entries.map(e => e.id), ['active']);
    assert.deepEqual(JSON.parse(payload).pi_command, ['pi']);
  } finally {
    if (previousPi) process.env.AUTOHARNESS_PI_BIN = previousPi;
    if (previousPython) process.env.AUTOHARNESS_PI_PYTHON = previousPython;
    else delete process.env.AUTOHARNESS_PI_PYTHON;
  }
});

test('child sessions expose only staging and enforce a fail-closed tool allowlist', async () => {
  try {
    const h = await harness({ AUTOHARNESS_PI_CHILD_SESSION: '1' });
    assert.deepEqual([...h.tools.keys()], ['stage_skill']);
    assert.equal(h.handlers.has('agent_settled'), false);
    assert.equal(h.commands.size, 0);
    assert.equal((await h.handlers.get('tool_call')({ toolName: 'bash' }, h.ctx)).block, true);
    assert.equal(await h.handlers.get('tool_call')({ toolName: 'read' }, h.ctx), undefined);
  } finally { delete process.env.AUTOHARNESS_PI_CHILD_SESSION; }
});

test('generic Claude markers and Python settings cannot disable or redirect native Pi', async () => {
  const h = await harness({ AUTOHARNESS_CHILD_SESSION: '1', AUTOHARNESS_DISABLE_GLOBAL: '1',
    AUTOHARNESS_PYTHON: '/does/not/exist/claude-python', AUTOHARNESS_PROJECT_ROOT: '/foreign' });
  assert.ok(h.commands.has('learn'));
  await h.handlers.get('session_start')({}, h.ctx);
  const result = await h.tools.get('stage_skill').execute('call', { ...proposal, level: 'global' }, undefined, undefined, h.ctx);
  assert.equal(result.isError, false);
  await h.handlers.get('agent_settled')({}, h.ctx);
  assert.match(await readFile(resolve(h.agentDir, 'skills/test-workflow/SKILL.md'), 'utf8'), /Run focused/);
  assert.equal(h.notices.filter(text => /Python.*required|ENOENT/.test(text)).length, 0);
});
