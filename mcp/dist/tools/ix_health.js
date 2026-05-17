import { statusRuntime } from "../lib/runtime-client.js";
import { wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_health";
const inputSchema = {};
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "Check whether the Ix Core Runtime is available and the graph is ready",
        schema: inputSchema,
        handler: runHealthCheck,
    });
}
async function runHealthCheck(input) {
    const response = await statusRuntime();
    if (!response.ok) {
        return wrapOk(TOOL_NAME, input, { graph_ready: false, runtime_available: false, version: null }, "Runtime unavailable — graph not ready", [
            "## ix_health",
            "",
            "**Status: UNAVAILABLE**",
            "",
            `The Ix Core Runtime is not reachable.`,
            `**Error:** ${response.message}`,
            "",
            "Gemini can continue without Ix context; graph-dependent features will be skipped.",
        ].join("\n"), null, undefined, response.duration_ms);
    }
    const raw = response.data;
    const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? raw.graph_revision ?? null;
    const status = raw.status ?? "ready";
    const version = raw.version ?? null;
    const graphReady = status === "ready" || status === "degraded";
    const preview_markdown = raw.preview_markdown ?? [
        `## ix_health`,
        "",
        `**Status:** ${status.toUpperCase()}`,
        version ? `**Runtime version:** ${version}` : "",
        canonical_revision !== null ? `**Graph revision:** ${canonical_revision}` : "",
        raw.last_ingest_at ? `**Last ingest:** ${raw.last_ingest_at}` : "",
        raw.stale ? "**Warning:** Index is stale" : "",
    ].filter(Boolean).join("\n");
    return wrapOk(TOOL_NAME, input, {
        graph_ready: graphReady,
        runtime_available: true,
        version,
        status,
        canonical_revision,
        last_ingest_at: raw.last_ingest_at ?? null,
        stale: raw.stale ?? false,
        capabilities: raw.capabilities ?? [],
    }, `ix runtime ${status}${version ? ` v${version}` : ""}`, preview_markdown, canonical_revision, undefined, response.duration_ms);
}
//# sourceMappingURL=ix_health.js.map