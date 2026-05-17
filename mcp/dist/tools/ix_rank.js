import { z } from "zod";
import { runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { insightsDeriveRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_rank";
const inputSchema = {
    by: z.enum(["dependents", "callers", "importers", "members"]).optional(),
    kind: z.enum(["class", "function", "file", "interface", "module"]).optional(),
    top: z.number().int().positive().max(50).optional(),
    path: z.string().min(1).optional(),
};
const DEFAULT_BY = "dependents";
const DEFAULT_KIND = "class";
const DEFAULT_TOP = 10;
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "Rank symbols by a quality metric (dependents, callers, importers, members) to surface hotspots",
        schema: inputSchema,
        handler: runRank,
    });
}
async function runRank(input) {
    const by = input.by ?? DEFAULT_BY;
    const kind = input.kind ?? DEFAULT_KIND;
    const top = input.top ?? DEFAULT_TOP;
    const body = { metric: "rank", by, kind, top };
    if (input.path)
        body["path"] = input.path;
    const response = await insightsDeriveRuntime(body);
    if (!response.ok) {
        const args = ["rank", "--by", by, "--kind", kind, "--top", String(top)];
        if (input.path)
            args.push("--path", input.path);
        const cliResult = await runIx(args);
        if (cliResult.ok) {
            const raw = parseIxJson(cliResult.stdout);
            const results = Array.isArray(raw.results) ? raw.results : [];
            const normalized = results.map((r) => ({
                name: r.name ?? null,
                kind: r.kind ?? null,
                score: r.score ?? null,
                path: r.path ?? null,
            }));
            const summary = raw.summary ?? {};
            const count = normalized.length;
            const summaryText = count === 0
                ? `No ${kind} entities ranked by ${by}`
                : `Top ${count} ${kind} entities ranked by ${by}`;
            return wrapOk(TOOL_NAME, { by, kind, top, path: input.path }, {
                metric: raw.metric ?? by,
                kind: raw.kind ?? kind,
                results: normalized,
                summary: {
                    evaluated: summary.evaluated ?? 0,
                    returned: summary.returned ?? count,
                },
                fallback: "cli",
            }, summaryText, raw.preview_markdown ?? buildRankPreview(by, kind, normalized), raw.canonical_revision ?? null, undefined, cliResult.durationMs);
        }
        return wrapErr(TOOL_NAME, { by, kind, top, path: input.path }, {
            code: response.code,
            message: response.message,
        });
    }
    const raw = response.data;
    const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
    const results = Array.isArray(raw.results) ? raw.results : [];
    const normalized = results.map((r) => ({
        name: r.name ?? null,
        kind: r.kind ?? null,
        score: r.score ?? null,
        path: r.path ?? null,
    }));
    const summary = raw.summary ?? {};
    const count = normalized.length;
    const summaryText = count === 0
        ? `No ${kind} entities ranked by ${by}`
        : `Top ${count} ${kind} entities ranked by ${by}`;
    const preview_markdown = raw.preview_markdown ?? buildRankPreview(by, kind, normalized);
    return wrapOk(TOOL_NAME, { by, kind, top, path: input.path }, {
        metric: raw.metric ?? by,
        kind: raw.kind ?? kind,
        results: normalized,
        summary: {
            evaluated: summary.evaluated ?? 0,
            returned: summary.returned ?? count,
        },
    }, summaryText, preview_markdown, canonical_revision, undefined, response.duration_ms);
}
function buildRankPreview(by, kind, results) {
    if (results.length === 0) {
        return `## ix_rank\n\nNo ${kind} entities found for metric: ${by}`;
    }
    const lines = [`## ix_rank (by: ${by}, kind: ${kind})`, ""];
    results.slice(0, 10).forEach((r, i) => {
        const score = r.score != null ? ` (${r.score})` : "";
        const path = r.path ? ` — \`${r.path}\`` : "";
        lines.push(`${i + 1}. \`${r.name ?? "?"}\`${score}${path}`);
    });
    return lines.join("\n");
}
//# sourceMappingURL=ix_rank.js.map