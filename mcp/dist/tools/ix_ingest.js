import { z } from "zod";
import { TIMEOUT_INGEST_MS } from "../lib/config.js";
import { runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { ingestRuntime } from "../lib/runtime-client.js";
import { wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_ingest";
const inputSchema = {
    paths: z.array(z.string().min(1)).min(1).describe("File paths to ingest into the graph after a write or edit. Pass all paths touched in the current edit."),
    async_mode: z.boolean().optional().describe("If true, start the ingest job and return immediately without waiting for completion. " +
        "Default: false (wait for completion)."),
    full_workspace: z.boolean().optional().describe("If true, run a full workspace reindex instead of a targeted file ingest. " +
        "Use at session end; slower than targeted ingest."),
};
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "Post-edit graph ingest. Call this after writing or editing any file to keep the Ix graph current. " +
            "Pass all file paths touched in the current operation. " +
            "Use full_workspace=true at session end for a complete graph refresh. " +
            "If the runtime is unavailable, returns a non-fatal warning (failClosed: false).",
        schema: inputSchema,
        handler: runIngest,
    });
}
async function runIngest(input) {
    const body = {
        paths: input.full_workspace ? [] : input.paths,
        options: {
            async: input.async_mode ?? false,
            full_workspace: input.full_workspace ?? false,
        },
    };
    const response = await ingestRuntime(body);
    if (!response.ok) {
        const cliResult = await runIx(["map"], { timeout: TIMEOUT_INGEST_MS });
        if (cliResult.ok) {
            const raw = parseIxJson(cliResult.stdout);
            const statusResult = await runIx(["status"]);
            const status = statusResult.ok
                ? parseIxJson(statusResult.stdout)
                : null;
            const canonical_revision = raw.map_rev ?? status?.currentRev ?? null;
            const filesIndexed = input.full_workspace
                ? raw.file_count ?? input.paths.length
                : input.paths.length;
            const stale = (status?.staleFiles ?? 0) > 0;
            const summary = input.full_workspace
                ? `Full workspace reindex completed at revision ${canonical_revision ?? "unknown"}`
                : `CLI reindex completed after ${filesIndexed} file${filesIndexed === 1 ? "" : "s"} changed`;
            const preview_markdown = [
                input.full_workspace
                    ? "## ix_ingest: Full workspace reindex"
                    : `## ix_ingest: CLI reindex after ${filesIndexed} file${filesIndexed === 1 ? "" : "s"} changed`,
                "",
                "**Mode:** CLI fallback (`ix map`)",
                raw.outcome ? `**Outcome:** ${raw.outcome}` : "",
                canonical_revision !== null ? `**Graph revision:** ${canonical_revision}` : "",
                status?.lastIngestAt ? `**Last ingest:** ${status.lastIngestAt}` : "",
                stale ? "**Warning:** Index still reports stale files after fallback." : "",
                !input.full_workspace ? "**Files:**" : "",
                ...(!input.full_workspace ? input.paths.map((path) => `- \`${path}\``) : []),
            ]
                .filter(Boolean)
                .join("\n");
            return wrapOk(TOOL_NAME, input, {
                ingested: true,
                files_indexed: filesIndexed,
                job_id: null,
                status: "complete",
                errors: [],
                runtime_available: true,
                fallback: "cli",
                map_outcome: raw.outcome ?? null,
                region_count: raw.region_count ?? null,
                stale,
            }, summary, preview_markdown, canonical_revision, undefined, cliResult.durationMs + (statusResult.ok ? statusResult.durationMs : 0));
        }
        // failClosed: false — runtime unavailability is non-fatal
        const preview_markdown = `**ix_ingest**: Runtime unavailable — graph not updated.\n\n` +
            `The Ix graph could not be updated after this edit. Graph context may be stale.\n\n` +
            `Error: ${response.message}`;
        return wrapOk(TOOL_NAME, input, { ingested: false, reason: `Runtime unavailable: ${response.message}`, runtime_available: false }, "Runtime unavailable — graph not updated", preview_markdown, null, undefined, response.duration_ms);
    }
    const raw = response.data;
    const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
    const filesIndexed = raw.files_indexed ?? input.paths.length;
    const errors = Array.isArray(raw.errors) && raw.errors.length > 0 ? raw.errors : null;
    const preview_markdown = raw.preview_markdown ??
        buildIngestPreview(input, filesIndexed, canonical_revision, errors);
    const summary = input.full_workspace
        ? `Full workspace reindex completed at revision ${canonical_revision ?? "unknown"}`
        : `Ingested ${filesIndexed} file${filesIndexed === 1 ? "" : "s"} at revision ${canonical_revision ?? "unknown"}`;
    return wrapOk(TOOL_NAME, input, {
        ingested: true,
        files_indexed: filesIndexed,
        job_id: raw.job_id ?? null,
        status: raw.status ?? "complete",
        errors: errors ?? [],
        runtime_available: true,
    }, summary, preview_markdown, canonical_revision, undefined, response.duration_ms);
}
function buildIngestPreview(input, filesIndexed, revision, errors) {
    const lines = [];
    if (input.full_workspace) {
        lines.push("## ix_ingest: Full workspace reindex");
    }
    else {
        lines.push(`## ix_ingest: ${filesIndexed} file${filesIndexed === 1 ? "" : "s"} ingested`);
        lines.push("");
        lines.push("**Files:**");
        for (const p of input.paths) {
            lines.push(`- \`${p}\``);
        }
    }
    if (revision !== null) {
        lines.push("");
        lines.push(`**Graph revision:** ${revision}`);
    }
    if (errors && errors.length > 0) {
        lines.push("");
        lines.push("**Errors:**");
        for (const e of errors) {
            lines.push(`- ${e}`);
        }
    }
    return lines.join("\n");
}
//# sourceMappingURL=ix_ingest.js.map