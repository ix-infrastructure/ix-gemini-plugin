import { z } from "zod";
import { cliStructuredError, runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_explain";
const inputSchema = {
    symbol: z.string().min(1, "symbol is required"),
};
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "Explain a symbol's role, importance, callers, and callees using graph data",
        schema: inputSchema,
        handler: runExplain,
    });
}
async function runExplain(input) {
    const response = await graphQueryRuntime({
        operation: "explain",
        selectors: [{ kind: "symbol", value: input.symbol }],
    });
    if (!response.ok) {
        const cliResult = await runIx(["explain", input.symbol]);
        if (cliResult.ok) {
            const raw = parseIxJson(cliResult.stdout);
            return renderExplainResult(input, raw, cliResult.durationMs);
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
    return renderExplainResult(input, raw, response.duration_ms, response.canonical_revision ?? raw.canonical_revision ?? null);
}
function renderExplainResult(input, raw, durationMs, canonicalRevision = raw.canonical_revision ?? null) {
    const target = raw.resolvedTarget;
    const facts = raw.facts;
    const rendered = raw.rendered;
    const data = {
        resolved_target: target
            ? { id: target.id ?? null, kind: target.kind ?? null, name: target.name ?? null, path: target.path ?? null }
            : null,
        facts: facts
            ? {
                id: facts.id ?? null,
                name: facts.name ?? null,
                kind: facts.kind ?? null,
                path: facts.path ?? null,
                container: facts.container ?? null,
                members: facts.members ?? [],
                member_count: facts.memberCount ?? 0,
                caller_count: facts.callerCount ?? 0,
                callee_count: facts.calleeCount ?? 0,
                dependent_count: facts.dependentCount ?? 0,
                importer_count: facts.importerCount ?? 0,
                top_callers: facts.topCallers ?? [],
                top_dependents: facts.topDependents ?? [],
                stale: facts.stale ?? false,
            }
            : null,
        role: raw.role
            ? { role: raw.role.role ?? null, confidence: raw.role.confidence ?? null, reasons: raw.role.reasons ?? [] }
            : null,
        importance: raw.importance
            ? { level: raw.importance.level ?? null, category: raw.importance.category ?? null, reasons: raw.importance.reasons ?? [] }
            : null,
        rendered: rendered
            ? {
                explanation: rendered.explanation ?? null,
                context: rendered.context ?? null,
                used_by: rendered.usedBy ?? null,
                why_it_matters: rendered.whyItMatters ?? null,
                notes: rendered.notes ?? [],
            }
            : null,
    };
    const name = target?.name ?? facts?.name ?? input.symbol;
    const summary = rendered?.explanation
        ? rendered.explanation
        : raw.importance?.level
            ? `${name} — ${raw.importance.level} importance`
            : `Explained ${name}`;
    const previewData = {
        role: data.role ? { role: data.role.role, confidence: data.role.confidence } : null,
        importance: data.importance ? { level: data.importance.level, category: data.importance.category } : null,
        facts: data.facts ? { caller_count: data.facts.caller_count, callee_count: data.facts.callee_count, dependent_count: data.facts.dependent_count } : null,
        rendered: data.rendered ? { explanation: data.rendered.explanation, why_it_matters: data.rendered.why_it_matters } : null,
    };
    const preview_markdown = raw.preview_markdown ?? buildExplainPreview(name, previewData);
    return wrapOk(TOOL_NAME, input, data, summary, preview_markdown, canonicalRevision, undefined, durationMs);
}
function buildExplainPreview(name, data) {
    const lines = [`## ix_explain: ${name}`, ""];
    if (data.role?.role)
        lines.push(`**Role:** ${data.role.role} (${data.role.confidence ?? "?"})`);
    if (data.importance?.level)
        lines.push(`**Importance:** ${data.importance.level} (${data.importance.category ?? "?"})`);
    if (data.facts) {
        const counts = [];
        if (data.facts.caller_count)
            counts.push(`${data.facts.caller_count} callers`);
        if (data.facts.callee_count)
            counts.push(`${data.facts.callee_count} callees`);
        if (data.facts.dependent_count)
            counts.push(`${data.facts.dependent_count} dependents`);
        if (counts.length > 0)
            lines.push(`**Metrics:** ${counts.join(" | ")}`);
    }
    if (data.rendered?.explanation) {
        lines.push("", `> ${data.rendered.explanation}`);
    }
    if (data.rendered?.why_it_matters) {
        lines.push("", `**Why it matters:** ${data.rendered.why_it_matters}`);
    }
    return lines.join("\n");
}
//# sourceMappingURL=ix_explain.js.map