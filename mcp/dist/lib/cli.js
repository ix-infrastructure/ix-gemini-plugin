import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { appendFile } from "node:fs/promises";
import { IX_BIN, IX_DEBUG_LOG, TIMEOUT_CLI_MIN_MS, timeoutFor } from "./config.js";
const execFileAsync = promisify(execFile);
async function debugLog(message) {
    if (!IX_DEBUG_LOG)
        return;
    const ts = new Date().toISOString();
    const line = `[${ts}] [ix-gemini-mcp-cli] ${message}\n`;
    try {
        await appendFile(IX_DEBUG_LOG, line, "utf8");
    }
    catch {
        // non-fatal
    }
}
export function stripHeader(raw) {
    const lines = raw.split("\n");
    const start = lines.findIndex((line) => /^\s*[\[{]/.test(line));
    if (start === -1)
        return raw;
    return lines.slice(start).join("\n");
}
export async function runIx(args, opts = {}) {
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
    }
    catch (err) {
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
function isExecError(err) {
    return err instanceof Error && ("stdout" in err || "stderr" in err);
}
//# sourceMappingURL=cli.js.map