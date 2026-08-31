import assert from "node:assert/strict";
import test, { after, before } from "node:test";
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * A stubbed `ix` that refuses the way the CLI does: the structured body on
 * stdout, a non-zero exit to match.
 *
 * One stub for the whole file, installed before any import of `lib/cli.js`,
 * because `config.ts` reads IX_BIN at module load. Two consequences, both of
 * which bit on the way here:
 *
 *  - a *static* import resolves IX_BIN to "ix" before any test body runs, and
 *    the suite then invokes the developer's real ix against their real graph —
 *    16s and an assertion that proves nothing;
 *  - re-assigning IX_BIN between tests does nothing, because the module is
 *    already evaluated. A second per-test stub only removed the first one from
 *    under the still-cached path.
 *
 * Node's test runner gives each file its own process, so this assignment cannot
 * leak into another suite.
 */
let dir: string;

before(() => {
  dir = mkdtempSync(join(tmpdir(), "ix-gemini-stub-"));
  const isWindows = process.platform === "win32";
  const stub = join(dir, isWindows ? "ix.cmd" : "ix");
  const body = '{"error":"unresolved_target","message":"No entity found matching \\"Nope\\"."}';
  writeFileSync(
    stub,
    isWindows
      ? `@echo off\r\necho ${body.replace(/"/g, '\\"')}\r\nexit /b 1\r\n`
      : `#!/bin/sh\ncat <<'JSON'\n${body}\nJSON\nexit 1\n`,
  );
  if (!isWindows) chmodSync(stub, 0o755);
  process.env["IX_BIN"] = stub;
});

after(() => rmSync(dir, { recursive: true, force: true }));

/** Without this, there is no body for `cliStructuredError` to read. */
test("runIx keeps stdout when ix exits non-zero", async () => {
  const { runIx, cliStructuredError } = await import("../../lib/cli.js");
  const run = await runIx(["impact", "Nope"]);

  assert.equal(run.ok, false, "a non-zero exit is still a failed run");
  assert.equal(run.stdout.trim().startsWith("{"), true, "stdout must survive the failure");
  assert.deepEqual(cliStructuredError(run), {
    code: "unresolved_target",
    message: 'No entity found matching "Nope".',
  });
});

/**
 * The behaviour this exists for. With the Core Runtime down these tools fall
 * back to the CLI; when the CLI then refuses, the tool used to report the
 * *runtime's* "unavailable" and drop the CLI's stdout on the floor — so a model
 * asking about a symbol that is not in the graph was told the backend was
 * broken.
 */
test("a tool reports the CLI's refusal, not the runtime's unavailability", async (t) => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("connect ECONNREFUSED"); };
  t.after(() => { globalThis.fetch = originalFetch; });

  const { registerAllTools } = await import("../../server.js");
  const callbacks = new Map<string, (i: unknown, e: unknown) => Promise<{ content: Array<{ text: string }> }>>();
  registerAllTools({
    tool: (name: string, _d: unknown, _p: unknown, cb: never) => { callbacks.set(name, cb); },
  } as never);

  const callback = callbacks.get("ix_impact");
  assert.ok(callback, "ix_impact should be registered");

  const payload = await callback({ target: "Nope" }, {});
  const response = JSON.parse(payload.content[0]?.text ?? "{}") as Record<string, unknown>;

  assert.equal(response["ok"], false);
  const error = response["error"] as { code?: string; message?: string } | undefined;
  assert.equal(error?.code, "unresolved_target", "the CLI's slug, not the runtime's code");
  assert.match(String(error?.message), /No entity found matching/);
});
