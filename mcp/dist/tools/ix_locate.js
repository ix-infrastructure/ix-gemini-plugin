import { z } from "zod";
import { cliStructuredError, runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_locate";
const inputSchema = {
    symbol: z.string().min(1, "symbol is required"),
};
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "Resolve a symbol to its canonical graph-backed target — returns path, line range, and hierarchy",
        schema: inputSchema,
        handler: runLocate,
    });
}
async function runLocate(input) {
    const response = await graphQueryRuntime({
        operation: "locate",
        selectors: [{ kind: "symbol", value: input.symbol }],
    });
    if (!response.ok) {
        const cliResult = await runIx(["locate", input.symbol]);
        if (cliResult.ok) {
            const raw = parseIxJson(cliResult.stdout);
            const target = raw.resolvedTarget;
            const lineRange = raw.lineRange ?? {};
            const match = target
                ? {
                    id: target.id ?? null,
                    kind: target.kind ?? null,
                    name: target.name ?? null,
                    path: target.path ?? null,
                    line_start: lineRange.start ?? null,
                    line_end: lineRange.end ?? null,
                }
                : null;
            const data = {
                match,
                resolution_mode: raw.resolutionMode ?? null,
                system_path: Array.isArray(raw.systemPath) ? raw.systemPath : [],
                has_map_data: raw.hasMapData ?? false,
                diagnostics: Array.isArray(raw.diagnostics) ? raw.diagnostics : [],
                fallback: "cli",
            };
            const summary = target
                ? `Resolved ${target.name ?? input.symbol} to ${target.path ?? "unknown path"}`
                : `No graph-backed match found for ${input.symbol}`;
            return wrapOk(TOOL_NAME, input, data, summary, raw.preview_markdown ?? buildLocatePreview(input.symbol, match, data.system_path), raw.canonical_revision ?? null, undefined, cliResult.durationMs);
        }
        // The CLI ran and refused for a reason of its own -- report that rather
        // than the runtime's "unavailable", which is merely how we got here.
        const cliError = cliStructuredError(cliResult);
        if (cliError) {
            return wrapErr(TOOL_NAME, input, cliError);
        }
        return wrapErr(TOOL_NAME, input, {
            code: response.code,
            message: response.message,
        });
    }
    const raw = response.data;
    const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
    const target = raw.resolvedTarget;
    const lineRange = raw.lineRange ?? {};
    const match = target
        ? {
            id: target.id ?? null,
            kind: target.kind ?? null,
            name: target.name ?? null,
            path: target.path ?? null,
            line_start: lineRange.start ?? null,
            line_end: lineRange.end ?? null,
        }
        : null;
    const data = {
        match,
        resolution_mode: raw.resolutionMode ?? null,
        system_path: Array.isArray(raw.systemPath) ? raw.systemPath : [],
        has_map_data: raw.hasMapData ?? false,
        diagnostics: Array.isArray(raw.diagnostics) ? raw.diagnostics : [],
    };
    const summary = target
        ? `Resolved ${target.name ?? input.symbol} to ${target.path ?? "unknown path"}`
        : `No graph-backed match found for ${input.symbol}`;
    const preview_markdown = raw.preview_markdown ?? buildLocatePreview(input.symbol, match, data.system_path);
    return wrapOk(TOOL_NAME, input, data, summary, preview_markdown, canonical_revision, undefined, response.duration_ms);
}
function buildLocatePreview(symbol, match, systemPath) {
    if (!match) {
        return `## ix_locate: ${symbol}\n\nNo match found in graph.`;
    }
    const lines = [
        `## ix_locate: ${symbol}`,
        "",
        `**Resolved:** \`${match.name ?? symbol}\` (${match.kind ?? "unknown"})`,
    ];
    if (match.path) {
        const lineInfo = match.line_start != null ? ` lines ${match.line_start}–${match.line_end ?? match.line_start}` : "";
        lines.push(`**Location:** \`${match.path}\`${lineInfo}`);
    }
    if (systemPath.length > 0) {
        lines.push(`**Path:** ${systemPath.map((s) => s.name).join(" › ")}`);
    }
    return lines.join("\n");
}
//# sourceMappingURL=ix_locate.js.map