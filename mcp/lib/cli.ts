import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { appendFile } from "node:fs/promises";

import { IX_BIN, IX_DEBUG_LOG, TIMEOUT_CLI_MIN_MS, timeoutFor } from "./config.js";

const execFileAsync = promisify(execFile);

export interface IxResult {
  ok: boolean;
  stdout: string;
  stderr: string;
  durationMs: number;
}

async function debugLog(message: string): Promise<void> {
  if (!IX_DEBUG_LOG) return;
  const ts = new Date().toISOString();
  const line = `[${ts}] [ix-gemini-mcp-cli] ${message}\n`;
  try {
    await appendFile(IX_DEBUG_LOG, line, "utf8");
  } catch {
    // non-fatal
  }
}

export function stripHeader(raw: string): string {
  const lines = raw.split("\n");
  const start = lines.findIndex((line) => /^\s*[\[{]/.test(line));
  if (start === -1) return raw;
  return lines.slice(start).join("\n");
}

export async function runIx(
  args: string[],
  opts: { timeout?: number } = {},
): Promise<IxResult> {
  const start = Date.now();
  const timeout = opts.timeout ?? Math.max(timeoutFor(args[0] ?? ""), TIMEOUT_CLI_MIN_MS);

  await debugLog(`CMD ${IX_BIN} ${[...args, "--format", "json"].join(" ")}`);

  try {
    const { stdout, stderr } = await execFileAsync(IX_BIN, [...args, "--format", "json"], {
      timeout,
      maxBuffer: 10 * 1024 * 1024,
    });

    if (stderr.trim()) {
      await debugLog(`STDERR ${stderr.trim().slice(0, 300)}`);
    }

    return {
      ok: true,
      stdout: stripHeader(stdout),
      stderr,
      durationMs: Date.now() - start,
    };
  } catch (err: unknown) {
    const durationMs = Date.now() - start;
    if (isExecError(err)) {
      const stderr = err.stderr ?? "";
      const stdout = stripHeader(err.stdout ?? "");
      if (stderr.trim()) {
        await debugLog(`STDERR ${stderr.trim().slice(0, 300)}`);
      }
      if (stdout.trim()) {
        await debugLog(`STDOUT ${stdout.trim().slice(0, 300)}`);
      }
      if (err.message) {
        await debugLog(`ERROR ${err.message}`);
      }
      return {
        ok: false,
        stdout,
        stderr,
        durationMs,
      };
    }

    await debugLog(`ERROR ${String(err)}`);
    return { ok: false, stdout: "", stderr: String(err), durationMs };
  }
}

/**
 * The CLI's own structured error, when a run that exited non-zero still printed
 * one.
 *
 * `ix` reports a refusal as `{"error": "<slug>", "message": "..."}` on stdout
 * and exits non-zero to match, so the exit code alone cannot tell a broken
 * install from a target that simply is not in the graph — the body can, and it
 * is the more specific of the two. Returns null when the run succeeded, printed
 * nothing, or printed something that is not one of those records, leaving the
 * caller's existing error path untouched.
 */
export function cliStructuredError(
  result: IxResult,
): { code: string; message: string } | null {
  if (result.ok || !result.stdout.trim()) return null;
  try {
    const body: unknown = JSON.parse(result.stdout);
    if (!body || typeof body !== "object") return null;
    const { error, message } = body as { error?: unknown; message?: unknown };
    if (typeof error !== "string" || !error) return null;
    return { code: error, message: typeof message === "string" && message ? message : error };
  } catch {
    // Not JSON — `--format text` prose, or a partial write. Nothing to surface.
    return null;
  }
}

interface ExecError extends Error {
  stdout?: string;
  stderr?: string;
}

function isExecError(err: unknown): err is ExecError {
  return err instanceof Error && ("stdout" in err || "stderr" in err);
}
