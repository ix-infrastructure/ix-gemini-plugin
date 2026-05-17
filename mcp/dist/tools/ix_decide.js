import { z } from "zod";
import { runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { decideRuntime } from "../lib/runtime-client.js";
import { wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_decide";
const inputSchema = {
    paths: z.array(z.string().min(1)).min(1).describe("File paths that will be written or edited"),
    operation: z.enum(["write", "edit", "delete"]).describe("The type of file operation about to be performed"),
    context: z.string().optional().describe("Brief description of why this change is being made; helps the policy engine"),
    freshness_policy: z
        .enum(["same_revision_or_fail", "latest_indexed_ok", "allow_stale_with_warning"])
        .optional()
        .describe("How to handle stale index; defaults to latest_indexed_ok"),
};
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "Pre-edit policy gate. Call this before writing, editing, or deleting any file. " +
            "Returns verdict: allow | warn | block. " +
            "A 'block' verdict means the operation poses high risk based on graph evidence; proceed only with explicit user confirmation. " +
            "A 'warn' verdict means proceed with caution and document the rationale. " +
            "If the runtime is unavailable, defaults to allow (failClosed: false).",
        schema: inputSchema,
        handler: runDecide,
    });
}
async function runDecide(input) {
    const body = {
        paths: input.paths,
        operation: input.operation,
        freshness_policy: input.freshness_policy ?? "latest_indexed_ok",
    };
    if (input.context)
        body["context"] = input.context;
    const response = await decideRuntime(body);
    if (!response.ok) {
        const cliResult = await runIx(["status"]);
        if (cliResult.ok) {
            const raw = parseIxJson(cliResult.stdout);
            const revision = raw.currentRev ?? null;
            const stale = (raw.staleFiles ?? 0) > 0;
            const verdict = stale ? "warn" : "allow";
            const reason = stale
                ? "Policy runtime unavailable; local CLI reports a stale index, so proceed with caution."
                : "Policy runtime unavailable; local CLI is healthy, but no graph policy verdict is available, so allowing by default.";
            const preview_markdown = [
                `## ix_decide: ${verdict.toUpperCase()}`,
                "",
                verdict === "warn"
                    ? "**WARN** — Proceed with caution. Local Ix status is available, but the policy endpoint is unavailable and the index is stale."
                    : "**ALLOW** — Local Ix status is available, but the policy endpoint is unavailable, so this is an allow-by-default fallback.",
                "",
                "**Paths:**",
                ...input.paths.map((path) => `- \`${path}\``),
                "",
                `**Reason:** ${reason}`,
                revision !== null ? `**Revision:** ${revision}` : "",
            ]
                .filter(Boolean)
                .join("\n");
            return wrapOk(TOOL_NAME, input, {
                verdict,
                reason,
                runtime_available: true,
                backend: raw.backend ?? null,
                stale,
                fallback: "cli",
            }, `ix_decide: ${verdict} — ${reason.slice(0, 120)}`, preview_markdown, revision, undefined, cliResult.durationMs);
        }
        // failClosed: false — runtime unavailability is non-fatal; default to allow
        const preview_markdown = `**ix_decide**: Runtime unavailable — defaulting to **allow**.\n\n` +
            `Proceed with caution: Ix graph context is not available for this decision.\n\n` +
            `Error: ${response.message}`;
        return wrapOk(TOOL_NAME, input, { verdict: "allow", reason: `Runtime unavailable: ${response.message}`, runtime_available: false }, "Runtime unavailable — defaulting to allow", preview_markdown, null, undefined, response.duration_ms);
    }
    const raw = response.data;
    const verdict = raw.verdict ?? "allow";
    const reason = raw.reason ?? "";
    const canonical_revision = response.canonical_revision;
    const preview_markdown = raw.preview_markdown ?? buildDecidePreview(verdict, reason, input.paths);
    const evidence = Array.isArray(raw.evidence)
        ? raw.evidence.map((e) => {
            const item = { kind: (e.kind ?? "graph") };
            if (e.id !== undefined)
                item.id = e.id;
            if (e.name !== undefined)
                item.name = e.name;
            if (e.confidence !== undefined)
                item.confidence = e.confidence;
            return item;
        })
        : undefined;
    return wrapOk(TOOL_NAME, input, {
        verdict,
        reason,
        conflict_severity: raw.conflict_severity ?? null,
        runtime_available: true,
    }, `ix_decide: ${verdict} — ${reason.slice(0, 120)}`, preview_markdown, canonical_revision, evidence, response.duration_ms);
}
function buildDecidePreview(verdict, reason, paths) {
    const pathList = paths.map((p) => `- \`${p}\``).join("\n");
    const verdictLine = verdict === "block"
        ? "**BLOCK** — High-risk operation. Do not proceed without explicit user confirmation."
        : verdict === "warn"
            ? "**WARN** — Proceed with caution and document your rationale."
            : "**ALLOW** — Operation is safe to proceed.";
    return [
        `## ix_decide: ${verdict.toUpperCase()}`,
        "",
        verdictLine,
        "",
        "**Paths:**",
        pathList,
        "",
        reason ? `**Reason:** ${reason}` : "",
    ]
        .filter((line) => line !== undefined)
        .join("\n")
        .trim();
}
//# sourceMappingURL=ix_decide.js.map