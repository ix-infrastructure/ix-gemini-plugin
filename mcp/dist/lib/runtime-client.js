import { appendFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { IX_API_VERSION, IX_DEBUG_LOG, IX_FAIL_CLOSED, IX_RUNTIME_URL, IX_WORKSPACE_ID, SURFACE, SURFACE_VERSION, timeoutFor, } from "./config.js";
import { IxError } from "./errors.js";
// ── Debug log ─────────────────────────────────────────────────────────────────
async function debugLog(message) {
    if (!IX_DEBUG_LOG)
        return;
    const ts = new Date().toISOString();
    const line = `[${ts}] [ix-gemini-mcp] ${message}\n`;
    try {
        await appendFile(IX_DEBUG_LOG, line, "utf8");
    }
    catch {
        // non-fatal
    }
}
// ── Shared envelope fields ────────────────────────────────────────────────────
function baseEnvelope() {
    return {
        api_version: IX_API_VERSION,
        request_id: randomUUID(),
        ...(IX_WORKSPACE_ID ? { workspace_id: IX_WORKSPACE_ID } : {}),
        caller: {
            surface: SURFACE,
            surface_version: SURFACE_VERSION,
        },
    };
}
// ── HTTP helpers ──────────────────────────────────────────────────────────────
async function postJson(path, body) {
    const url = `${IX_RUNTIME_URL}${path}`;
    const payload = { ...baseEnvelope(), ...body };
    const timeout = timeoutFor(path);
    const start = Date.now();
    await debugLog(`POST ${url} ${JSON.stringify(payload).slice(0, 200)}`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            signal: controller.signal,
        });
        clearTimeout(timer);
        const duration_ms = Date.now() - start;
        const text = await response.text();
        if (!response.ok) {
            let errorCode = "IX_UPSTREAM_UNAVAILABLE";
            let errorMessage = `Runtime returned HTTP ${response.status}`;
            try {
                const errBody = JSON.parse(text);
                if (typeof errBody["code"] === "string")
                    errorCode = errBody["code"];
                if (typeof errBody["message"] === "string")
                    errorMessage = errBody["message"];
            }
            catch {
                // ignore parse failure; use defaults
            }
            await debugLog(`ERROR ${errorCode}: ${errorMessage}`);
            return { ok: false, code: errorCode, message: errorMessage, duration_ms };
        }
        const data = JSON.parse(text);
        const canonical_revision = typeof data["canonical_revision"] === "number"
            ? data["canonical_revision"]
            : null;
        return { ok: true, data, canonical_revision, duration_ms };
    }
    catch (err) {
        clearTimeout(timer);
        const duration_ms = Date.now() - start;
        if (err instanceof Error && err.name === "AbortError") {
            await debugLog(`TIMEOUT POST ${url} after ${timeout}ms`);
            if (IX_FAIL_CLOSED) {
                throw new IxError("TIMEOUT", `Runtime call timed out after ${timeout}ms`, err);
            }
            return { ok: false, code: "TIMEOUT", message: `Runtime call timed out after ${timeout}ms`, duration_ms };
        }
        const message = err instanceof Error ? err.message : String(err);
        await debugLog(`UNAVAILABLE POST ${url}: ${message}`);
        if (IX_FAIL_CLOSED) {
            throw new IxError("IX_UPSTREAM_UNAVAILABLE", `Runtime unavailable: ${message}`, err);
        }
        return { ok: false, code: "IX_UPSTREAM_UNAVAILABLE", message: `Runtime unavailable: ${message}`, duration_ms };
    }
}
async function getJson(path, params) {
    const url = new URL(`${IX_RUNTIME_URL}${path}`);
    const start = Date.now();
    if (params) {
        for (const [key, value] of Object.entries(params)) {
            url.searchParams.set(key, value);
        }
    }
    const timeout = timeoutFor(path);
    await debugLog(`GET ${url.toString()}`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(url.toString(), {
            method: "GET",
            headers: {
                "X-Surface": SURFACE,
                "X-Surface-Version": SURFACE_VERSION,
                "X-Api-Version": IX_API_VERSION,
                ...(IX_WORKSPACE_ID ? { "X-Workspace-Id": IX_WORKSPACE_ID } : {}),
            },
            signal: controller.signal,
        });
        clearTimeout(timer);
        const duration_ms = Date.now() - start;
        const text = await response.text();
        if (!response.ok) {
            let errorCode = "IX_UPSTREAM_UNAVAILABLE";
            let errorMessage = `Runtime returned HTTP ${response.status}`;
            try {
                const errBody = JSON.parse(text);
                if (typeof errBody["code"] === "string")
                    errorCode = errBody["code"];
                if (typeof errBody["message"] === "string")
                    errorMessage = errBody["message"];
            }
            catch {
                // ignore
            }
            return { ok: false, code: errorCode, message: errorMessage, duration_ms };
        }
        const data = JSON.parse(text);
        const canonical_revision = typeof data["canonical_revision"] === "number"
            ? data["canonical_revision"]
            : null;
        return { ok: true, data, canonical_revision, duration_ms };
    }
    catch (err) {
        clearTimeout(timer);
        const duration_ms = Date.now() - start;
        if (err instanceof Error && err.name === "AbortError") {
            await debugLog(`TIMEOUT GET ${url.toString()} after ${timeout}ms`);
            if (IX_FAIL_CLOSED) {
                throw new IxError("TIMEOUT", `Runtime call timed out after ${timeout}ms`, err);
            }
            return { ok: false, code: "TIMEOUT", message: `Runtime call timed out after ${timeout}ms`, duration_ms };
        }
        const message = err instanceof Error ? err.message : String(err);
        await debugLog(`UNAVAILABLE GET ${url.toString()}: ${message}`);
        if (IX_FAIL_CLOSED) {
            throw new IxError("IX_UPSTREAM_UNAVAILABLE", `Runtime unavailable: ${message}`, err);
        }
        return { ok: false, code: "IX_UPSTREAM_UNAVAILABLE", message: `Runtime unavailable: ${message}`, duration_ms };
    }
}
// ── Public API endpoints ──────────────────────────────────────────────────────
export async function queryRuntime(body) {
    return postJson("/v2/ix_query", body);
}
export async function decideRuntime(body) {
    return postJson("/v2/ix_decide", body);
}
export async function ingestRuntime(body) {
    return postJson("/v2/ingest/map", body);
}
export async function statusRuntime() {
    return getJson("/v2/status");
}
export async function graphQueryRuntime(body) {
    return postJson("/v2/graph/query", body);
}
export async function insightsDeriveRuntime(body) {
    return postJson("/v2/insights/derive", body);
}
export async function briefingRuntime() {
    return getJson("/v2/briefing");
}
//# sourceMappingURL=runtime-client.js.map