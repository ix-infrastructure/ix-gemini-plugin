import { z } from "zod";
import { insightsDeriveRuntime } from "../lib/runtime-client.js";
import { wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_smells";
const DEFAULT_LIMIT = 50;
const inputSchema = {
    path: z.string().min(1).optional(),
    limit: z.number().int().positive().max(200).optional(),
};
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "Detect code quality smells across the graph — orphan files, high coupling, etc.",
        schema: inputSchema,
        handler: runSmells,
    });
}
async function runSmells(input) {
    const limit = input.limit ?? DEFAULT_LIMIT;
    const body = { metric: "smells", limit };
    if (input.path)
        body["path"] = input.path;
    const response = await insightsDeriveRuntime(body);
    if (!response.ok) {
        return wrapOk(TOOL_NAME, { ...input, limit }, { candidates: [], total: 0, runtime_available: false }, "Runtime unavailable — no smells data", `## ix_smells: Unavailable\n\n**Error:** ${response.message}`, null, undefined, response.duration_ms);
    }
    const raw = response.data;
    const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
    const allCandidates = Array.isArray(raw.candidates) ? raw.candidates : [];
    const candidates = allCandidates.slice(0, limit).map((c) => ({
        file: c.file ?? null,
        smell: c.smell ?? null,
        confidence: c.confidence ?? null,
        signals: c.signals ?? {},
    }));
    const total = raw.count ?? allCandidates.length;
    const returned = candidates.length;
    const summary = total === 0
        ? "No code smells detected"
        : returned < total
            ? `Found ${total} code smells (showing ${returned})`
            : `Found ${total} code smells`;
    const preview_markdown = raw.preview_markdown ?? buildSmellsPreview(candidates, total);
    return wrapOk(TOOL_NAME, { ...input, limit }, {
        candidates,
        total,
        returned,
        rev: raw.rev ?? null,
        run_at: raw.run_at ?? null,
        inference_version: raw.inference_version ?? null,
    }, summary, preview_markdown, canonical_revision, undefined, response.duration_ms);
}
function buildSmellsPreview(candidates, total) {
    if (total === 0)
        return `## ix_smells\n\nNo code smells detected.`;
    const lines = [`## ix_smells`, "", `**${total} smell${total === 1 ? "" : "s"} detected**`, ""];
    for (const c of candidates.slice(0, 15)) {
        const conf = c.confidence != null ? ` (${(c.confidence * 100).toFixed(0)}%)` : "";
        lines.push(`- \`${c.file ?? "?"}\`: ${c.smell ?? "unknown"}${conf}`);
    }
    if (total > 15)
        lines.push(`\n_...and ${total - 15} more_`);
    return lines.join("\n");
}
//# sourceMappingURL=ix_smells.js.map