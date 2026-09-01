import assert from "node:assert/strict";
import test from "node:test";
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { cliStructuredError, type IxResult } from "../../lib/cli.js";

function result(over: Partial<IxResult>): IxResult {
  return { ok: false, stdout: "", stderr: "", durationMs: 1, ...over };
}

/**
 * `ix` reports a refusal as `{"error": "<slug>", "message": "..."}` on stdout
 * and exits non-zero to match. The exit code alone cannot tell a broken install
 * from a target that is simply not in the graph; the body can.
 */
test("cliStructuredError reads the CLI's own error off a failed run", () => {
  const err = cliStructuredError(
    result({ stdout: '{"error":"unresolved_target","message":"No entity found matching \\"Nope\\"."}' }),
  );

  assert.deepEqual(err, {
    code: "unresolved_target",
    message: 'No entity found matching "Nope".',
  });
});

test("cliStructuredError falls back to the slug when there is no message", () => {
  const err = cliStructuredError(result({ stdout: '{"error":"path_outside_workspace"}' }));
  assert.deepEqual(err, { code: "path_outside_workspace", message: "path_outside_workspace" });
});

test("cliStructuredError yields null when there is nothing to surface", () => {
  // A successful run is never an error, whatever it printed.
  assert.equal(cliStructuredError(result({ ok: true, stdout: '{"error":"x"}' })), null);
  // A failure that printed nothing: the caller's existing error path stands.
  assert.equal(cliStructuredError(result({ stderr: "ix: command not found" })), null);
  // Prose, a partial write, or a JSON shape that is not an error record.
  assert.equal(cliStructuredError(result({ stdout: "Error: something went wrong" })), null);
  assert.equal(cliStructuredError(result({ stdout: '{"error":' })), null);
  assert.equal(cliStructuredError(result({ stdout: '{"riskLevel":"low"}' })), null);
  assert.equal(cliStructuredError(result({ stdout: '{"error":42}' })), null);
  assert.equal(cliStructuredError(result({ stdout: "[]" })), null);
});
