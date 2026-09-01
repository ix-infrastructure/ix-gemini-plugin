import { z } from "zod";
import { cliStructuredError, runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const CALLERS_TOOL = "ix_callers";
const IMPORTED_BY_TOOL = "ix_imported_by";
const symbolSchema = {
    symbol: z.string().min(1, "symbol is required"),
};
export function register(server) {
    registerIxTool(server, {
        name: CALLERS_TOOL,
        description: "List entities that call a symbol (incoming call edges)",
        schema: symbolSchema,
        handler: (input) => runRelation(CALLERS_TOOL, "callers", input),
    });
    registerIxTool(server, {
        name: IMPORTED_BY_TOOL,
        description: "List files or symbols that import a given symbol (incoming import edges)",
        schema: symbolSchema,
        handler: (input) => runRelation(IMPORTED_BY_TOOL, "imported_by", input),
    });
}
async function runRelation(toolName, operation, input) {
    const response = await graphQueryRuntime({
        operation,
        selectors: [{ kind: "symbol", value: input.symbol }],
    });
    if (!response.ok) {
        const cliArgs = operation === "imported_by" ? ["imported-by", input.symbol] : ["callers", input.symbol];
        const cliResult = await runIx(cliArgs);
        if (cliResult.ok) {
            const raw = parseIxJson(cliResult.stdout);
            return buildRelationResult(toolName, input, raw, cliResult.durationMs);
        }
        // The CLI ran and refused for a reason of its own -- report that rather
        // than the runtime's "unavailable", which is merely how we got here.
        const cliError = cliStructuredError(cliResult);
        if (cliError) {
            return wrapErr(toolName, input, cliError);
        }
        return wrapErr(toolName, input, {
            code: response.code,
            message: response.message,
        });
    }
    const raw = response.data;
    return buildRelationResult(toolName, input, raw, response.duration_ms, response.canonical_revision ?? raw.canonical_revision ?? null);
}
function buildRelationResult(toolName, input, raw, durationMs, canonicalRevision = raw.canonical_revision ?? null) {
    const results = Array.isArray(raw.results) ? raw.results : [];
    const normalized = results.map((r) => ({
        name: r.name ?? null,
        kind: r.kind ?? null,
        id: r.id ?? null,
        path: r.path ?? null,
    }));
    const resolvedTarget = raw.resolvedTarget;
    const total = raw.summary?.total ?? normalized.length;
    const verb = toolName === IMPORTED_BY_TOOL ? "importers" : "callers";
    const summary = total === 0 ? `No ${verb} found for ${input.symbol}` : `Found ${total} ${verb} for ${input.symbol}`;
    const preview_markdown = raw.preview_markdown ?? buildRelationPreview(toolName, input.symbol, normalized, total);
    return wrapOk(toolName, input, {
        results: normalized,
        total,
        resolved_target: resolvedTarget
            ? {
                id: resolvedTarget.id ?? null,
                kind: resolvedTarget.kind ?? null,
                name: resolvedTarget.name ?? null,
                path: resolvedTarget.path ?? null,
                resolution_mode: resolvedTarget.resolutionMode ?? null,
            }
            : null,
        result_source: raw.resultSource ?? null,
        diagnostics: Array.isArray(raw.diagnostics)
            ? raw.diagnostics.map((d) => ({ code: d.code ?? null, message: d.message ?? null }))
            : [],
    }, summary, preview_markdown, canonicalRevision, undefined, durationMs);
}
function buildRelationPreview(toolName, symbol, results, total) {
    const verb = toolName === IMPORTED_BY_TOOL ? "importers" : "callers";
    if (total === 0)
        return `## ${toolName}: ${symbol}\n\nNo ${verb} found.`;
    const lines = [`## ${toolName}: ${symbol}`, "", `**${total} ${verb}**`, ""];
    for (const r of results.slice(0, 15)) {
        const kind = r.kind ? ` (${r.kind})` : "";
        const path = r.path ? ` — \`${r.path}\`` : "";
        lines.push(`- \`${r.name ?? "?"}\`${kind}${path}`);
    }
    if (total > 15)
        lines.push(`\n_...and ${total - 15} more_`);
    return lines.join("\n");
}
//# sourceMappingURL=ix_callers.js.map