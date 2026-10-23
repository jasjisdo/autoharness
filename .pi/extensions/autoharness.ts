import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, delimiter, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import type { TSchema } from "typebox";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const schema = JSON.parse(readFileSync(resolve(packageRoot, ".pi/stage-skill.schema.json"), "utf8")) as TSchema;
const INDEX_MARKER = "[AUTOHARNESS PI SKILL INDEX]";
const CURSOR_ENTRY = "autoharness:reflection-cursor";
const CHILD_TOOLS = new Set(["read", "grep", "find", "ls", "stage_skill"]);

type BridgeResult = {
  ok?: boolean;
  error?: string;
  context?: string | null;
  summary?: string | null;
  roots?: Record<string, string>;
  triggered?: boolean;
  verdicts?: Array<{ ok: boolean }>;
  curator?: { error?: string };
};

function piInvocation(): string[] {
  if (process.env.AUTOHARNESS_PI_BIN) return [process.env.AUTOHARNESS_PI_BIN];
  const script = process.argv[1];
  if (script && basename(script) === "cli.js" && /[\\/]pi-coding-agent[\\/]dist[\\/]cli\.js$/.test(script) && existsSync(script)) {
    return [process.execPath, script];
  }
  if (/^pi(?:\.exe)?$/.test(basename(process.execPath))) return [process.execPath];
  return ["pi"];
}

function runBridge(payload: Record<string, unknown>, signal?: AbortSignal): Promise<BridgeResult> {
  return new Promise((resolveResult, reject) => {
    const environment = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      !key.startsWith("AUTOHARNESS_") || key.startsWith("AUTOHARNESS_PI_")));
    const child = spawn(process.env.AUTOHARNESS_PI_PYTHON || "python3", ["-m", "autoharness.pi_bridge"], {
      cwd: String(payload.cwd),
      env: { ...environment, PYTHONPATH: [resolve(packageRoot, "src"), process.env.PYTHONPATH].filter(Boolean).join(delimiter) },
      stdio: ["pipe", "pipe", "pipe"],
      signal,
    });
    let output = "", errors = "";
    const timeout = setTimeout(() => child.kill("SIGKILL"), 30_000);
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      output += chunk;
      if (output.length > 1_000_000) child.kill("SIGKILL");
    });
    child.stderr.on("data", (chunk: string) => { errors = (errors + chunk).slice(-2000); });
    child.on("error", (error) => { clearTimeout(timeout); reject(error); });
    child.stdin.on("error", (error) => { clearTimeout(timeout); reject(error); });
    child.on("close", (code) => {
      clearTimeout(timeout);
      try {
        const result = JSON.parse(output) as BridgeResult;
        if (code !== 0) reject(new Error(result.error || `Python bridge exited ${code}: ${errors}`));
        else resolveResult(result);
      } catch (error) {
        reject(new Error(`autoharness: Python 3.11+ is required; bridge failed (${code}): ${errors || String(error)}`));
      }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

function captureBranch(ctx: ExtensionContext) {
  const entries = [];
  let bytes = 0;
  for (const entry of [...ctx.sessionManager.getBranch()].reverse()) {
    if (entry.type !== "message") continue;
    const message = entry.message;
    if (message.role !== "user" && message.role !== "assistant" && message.role !== "toolResult") continue;
    const content = typeof message.content === "string" ? message.content : message.content.filter(
      (part) => part.type === "text" || part.type === "toolCall",
    );
    const clean = { role: message.role, content,
      ...(message.role === "toolResult" ? { toolName: message.toolName, isError: message.isError } : {}) };
    const item = { type: "message", id: entry.id, message: clean };
    const size = Buffer.byteLength(JSON.stringify(item));
    // Omit oversized records rather than cutting secrets before Python redaction.
    if (bytes + size > 250_000 && entries.length > 0) break;
    if (size > 250_000) {
      item.message = { ...clean, content: [{ type: "text", text: "[AutoHarness omitted an oversized message before capture.]" }] };
    }
    entries.push(item);
    bytes += Math.min(size, 250_000);
  }
  return entries.reverse();
}

export default function autoharnessPiExtension(pi: ExtensionAPI) {
  let pending: Promise<unknown> = Promise.resolve();
  let context: string | null = null;
  let roots: Record<string, string> = {};
  let cursor: string | null = null;
  let timestamp = Date.now();

  function notify(ctx: ExtensionContext, error: unknown) {
    const text = `autoharness: ${error instanceof Error ? error.message : String(error)}`;
    if (ctx.hasUI) ctx.ui.notify(text, "warning");
    else console.error(text);
  }

  function request(ctx: ExtensionContext, op: string, extra: Record<string, unknown> = {}, signal?: AbortSignal) {
    const payload = {
      op, cwd: ctx.cwd, session_id: ctx.sessionManager.getSessionId(),
      agent_dir: resolve(process.env.PI_CODING_AGENT_DIR || resolve(homedir(), ".pi/agent")),
      provider: ctx.model?.provider, model: ctx.model?.id, pi_command: piInvocation(), ...extra,
    };
    const result = pending.then(() => runBridge(payload, signal));
    pending = result.catch(() => undefined);
    return result;
  }

  pi.registerTool({
    name: "stage_skill",
    label: "Stage skill",
    description: "Propose a learned skill change. Only queues an intent; the deterministic promoter validates and lands it after the run. Never edits user-authored skills.",
    parameters: schema,
    async execute(_id, params, signal, _onUpdate, ctx) {
      try {
        const result = await request(ctx, "stage", { params }, signal);
        return { content: [{ type: "text", text: JSON.stringify(result) }], details: result, isError: !result.ok };
      } catch (error) {
        return { content: [{ type: "text", text: `autoharness: ${String(error)}` }], details: undefined, isError: true };
      }
    },
  });

  if (process.env.AUTOHARNESS_PI_CHILD_SESSION) {
    pi.on("tool_call", async (event) => {
      if (!CHILD_TOOLS.has(event.toolName)) return { block: true, reason: "AutoHarness child sessions may only read and stage skill proposals." };
    });
    return;
  }

  pi.registerCommand("learn", {
    description: "Distill reusable lessons from this session through AutoHarness validation.",
    handler: async (args) => {
      const skill = readFileSync(resolve(packageRoot, "skills/learn/SKILL.md"), "utf8").replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "").trim();
      pi.sendUserMessage(`${skill}${args ? `\n\nUser request: ${args}` : ""}`, { deliverAs: "followUp" });
    },
  });

  pi.on("session_start", async (_event, ctx) => {
    context = null;
    roots = {};
    cursor = null;
    timestamp = Date.now();
    for (const entry of ctx.sessionManager.getBranch()) {
      if (entry.type === "custom" && entry.customType === CURSOR_ENTRY) {
        const data = entry.data as { leafId?: string } | undefined;
        cursor = data?.leafId || null;
      }
    }
    try {
      const result = await request(ctx, "session_start");
      roots = result.roots || {};
      context = result.context || null;
      if (result.error) notify(ctx, result.error);
      if (result.summary && ctx.hasUI) ctx.ui.notify(result.summary.split("\n\n")[0], "info");
    } catch (error) { notify(ctx, error); }
  });

  pi.on("resources_discover", async () => ({
    skillPaths: Object.values(roots).map((root) => resolve(root, "skills")).filter(existsSync),
  }));

  pi.on("context", async (event) => {
    if (!context) return;
    if (event.messages.some((message) => {
      const content = "content" in message ? message.content : undefined;
      return typeof content === "string" ? content.includes(INDEX_MARKER) : Array.isArray(content) && content.some(
        (part) => part.type === "text" && part.text.includes(INDEX_MARKER),
      );
    })) return;
    const index = { role: "user" as const, content: [{ type: "text" as const, text: `${INDEX_MARKER}\n${context}` }], timestamp };
    let position = 0;
    while (event.messages[position]?.role === "compactionSummary") position += 1;
    return { messages: [...event.messages.slice(0, position), index, ...event.messages.slice(position)] };
  });

  pi.on("tool_call", async (_event, ctx) => {
    try { await request(ctx, "tool_call"); }
    catch (error) { notify(ctx, error); }
  });

  pi.on("tool_result", async (event, ctx) => {
    if (event.toolName !== "read" || event.isError) return;
    const path = (event.input as { path?: unknown }).path;
    if (typeof path !== "string") return;
    try { await request(ctx, "skill_read", { path }); }
    catch (error) { notify(ctx, error); }
  });

  async function settle(ctx: ExtensionContext, op: "settled" | "shutdown") {
    try {
      const entries = captureBranch(ctx);
      const result = await request(ctx, op, { entries, since_id: cursor });
      context = result.context || null;
      if (result.triggered && entries.length) {
        cursor = entries.at(-1)!.id;
        pi.appendEntry(CURSOR_ENTRY, { leafId: cursor });
      }
      if (result.error) notify(ctx, result.error);
      if (result.curator?.error) notify(ctx, result.curator.error);
      if (result.verdicts?.length && ctx.hasUI) {
        const landed = result.verdicts.filter((verdict) => verdict.ok).length;
        ctx.ui.notify(`autoharness: landed ${landed}, rejected ${result.verdicts.length - landed}.`, "info");
      }
    } catch (error) { notify(ctx, error); }
  }

  pi.on("agent_settled", async (_event, ctx) => { await settle(ctx, "settled"); });
  pi.on("session_shutdown", async (_event, ctx) => { await settle(ctx, "shutdown"); });
  pi.on("session_compact", async (_event, ctx) => {
    try { context = (await request(ctx, "index")).context || null; }
    catch (error) { notify(ctx, error); }
  });
}
