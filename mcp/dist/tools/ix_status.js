import { runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { statusRuntime } from "../lib/runtime-client.js";
import { wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_status";
const inputSchema = {};
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "Check Ix Core Runtime health and graph readiness. " +
            "Call at session start to confirm the runtime is available and the graph is indexed. " +
            "Returns: status (ready | degraded | unavailable), canonical_revision, staleness, and capabilities. " +
            "If the runtime is unavailable, returns a non-fatal degraded status (failClosed: false).",
        schema: inputSchema,
        handler: runStatus,
    });
}
async function runStatus(input) {
    const response = await statusRuntime();
    if (!response.ok) {
        const cliResult = await runIx(["status"]);
        if (cliResult.ok) {
            const raw = parseIxJson(cliResult.stdout);
            const revision = raw.currentRev ?? null;
            const stale = (raw.staleFiles ?? 0) > 0;
            return wrapOk(TOOL_NAME, input, {
                status: raw.backend === "ok" ? "ready" : "degraded",
                canonical_revision: revision,
                last_ingest_at: raw.lastIngestAt ?? null,
                freshness_age_minutes: null,
                stale,
                capabilities: [],
                workspace_id: null,
                version: null,
                runtime_available: true,
                fallback: "cli",
            }, buildStatusSummary(raw.backend === "ok" ? "ready" : "degraded", revision, stale), buildStatusPreview({
                status: raw.backend === "ok" ? "ready" : "degraded",
                ...(revision !== null ? { graph_revision: revision } : {}),
                ...(raw.lastIngestAt ? { last_ingest_at: raw.lastIngestAt } : {}),
                stale,
            }, revision), revision, undefined, cliResult.durationMs);
        }
        // failClosed: false — unavailability is non-fatal; report clearly
        const preview_markdown = `## ix_status: UNAVAILABLE\n\n` +
            `The Ix Core Runtime is not reachable. Graph context is not available.\n\n` +
            `**Error:** ${response.message}\n\n` +
            `Gemini can continue without Ix context; graph-dependent features will be skipped.`;
        return wrapOk(TOOL_NAME, input, {
            status: "unavailable",
            runtime_available: false,
            reason: response.message,
        }, "Runtime unavailable", preview_markdown, null, undefined, response.duration_ms);
    }
    const raw = response.data;
    const status = raw.status ?? "ready";
    const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? raw.graph_revision ?? null;
    const preview_markdown = raw.preview_markdown ?? buildStatusPreview(raw, canonical_revision);
    const summary = buildStatusSummary(status, canonical_revision, raw.stale ?? false);
    return wrapOk(TOOL_NAME, input, {
        status,
        canonical_revision,
        last_ingest_at: raw.last_ingest_at ?? null,
        freshness_age_minutes: raw.freshness_age_minutes ?? null,
        stale: raw.stale ?? false,
        capabilities: raw.capabilities ?? [],
        workspace_id: raw.workspace_id ?? null,
        version: raw.version ?? null,
        runtime_available: true,
    }, summary, preview_markdown, canonical_revision, undefined, response.duration_ms);
}
function buildStatusSummary(status, revision, stale) {
    const revStr = revision !== null ? ` at revision ${revision}` : "";
    const staleStr = stale ? " (index stale)" : "";
    return `Runtime ${status}${revStr}${staleStr}`;
}
function buildStatusPreview(raw, revision) {
    const statusEmoji = raw.status === "ready" ? "Ready" : raw.status === "degraded" ? "Degraded" : "Unavailable";
    const lines = [
        `## ix_status: ${statusEmoji}`,
        "",
    ];
    if (revision !== null) {
        lines.push(`**Graph revision:** ${revision}`);
    }
    if (raw.last_ingest_at) {
        lines.push(`**Last ingest:** ${raw.last_ingest_at}`);
    }
    if (raw.freshness_age_minutes !== undefined) {
        lines.push(`**Index age:** ${raw.freshness_age_minutes} min${raw.stale ? " (stale)" : ""}`);
    }
    if (raw.version) {
        lines.push(`**Runtime version:** ${raw.version}`);
    }
    if (raw.capabilities && raw.capabilities.length > 0) {
        lines.push(`**Capabilities:** ${raw.capabilities.join(", ")}`);
    }
    return lines.join("\n");
}
//# sourceMappingURL=ix_status.js.map