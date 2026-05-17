// All plugin configuration comes from environment variables.
// Read once at import time so the values are stable for the process lifetime.
function envBool(name, defaultVal) {
    const v = process.env[name]?.toLowerCase();
    if (v === "true" || v === "1")
        return true;
    if (v === "false" || v === "0")
        return false;
    return defaultVal;
}
function envStr(name, defaultVal) {
    return process.env[name] ?? defaultVal;
}
function envNullable(name) {
    return process.env[name] ?? null;
}
// ── Runtime API ───────────────────────────────────────────────────────────────
export const IX_RUNTIME_URL = envStr("IX_RUNTIME_URL", "http://localhost:8090");
export const IX_WORKSPACE_ID = envNullable("IX_WORKSPACE_ID");
export const IX_API_VERSION = "v2";
export const IX_BIN = envStr("IX_BIN", "ix");
// ── Surface identity ──────────────────────────────────────────────────────────
export const SURFACE = "gemini-plugin";
export const SURFACE_VERSION = "0.1.0";
// ── Logging ───────────────────────────────────────────────────────────────────
export const IX_DEBUG_LOG = envNullable("IX_DEBUG_LOG");
// ── Behaviour flags ───────────────────────────────────────────────────────────
export const IX_FAIL_CLOSED = envBool("IX_FAIL_CLOSED", false);
// ── Timeouts (ms) ─────────────────────────────────────────────────────────────
export const TIMEOUT_DEFAULT_MS = 15_000;
export const TIMEOUT_INGEST_MS = 60_000;
export const TIMEOUT_STATUS_MS = 5_000;
export const TIMEOUT_DECIDE_MS = 10_000;
export const TIMEOUT_CLI_MIN_MS = 15_000;
export function timeoutFor(endpoint) {
    if (endpoint.includes("ingest/map"))
        return TIMEOUT_INGEST_MS;
    if (endpoint.includes("status"))
        return TIMEOUT_STATUS_MS;
    if (endpoint.includes("ix_decide"))
        return TIMEOUT_DECIDE_MS;
    return TIMEOUT_DEFAULT_MS;
}
//# sourceMappingURL=config.js.map