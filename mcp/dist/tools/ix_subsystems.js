import { runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_subsystems";
const inputSchema = {};
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "List graph-derived subsystems for top-level repository orientation",
        schema: inputSchema,
        handler: runSubsystems,
    });
}
async function runSubsystems(input) {
    const response = await graphQueryRuntime({ operation: "subsystems" });
    if (!response.ok) {
        const cliResult = await runIx(["subsystems"]);
        if (cliResult.ok) {
            const raw = parseIxJson(cliResult.stdout);
            const regions = Array.isArray(raw.regions) ? raw.regions : [];
            const subsystems = regions.map((r) => ({
                name: r.label ?? "unknown",
                purpose: inferPurpose(r),
                files: r.files ?? 0,
                level: r.level ?? null,
                kind: r.label_kind ?? null,
                children: r.children ?? 0,
                confidence: r.confidence ?? null,
                signals: Array.isArray(r.signals) ? r.signals : [],
                interfaces: r.interfaces ?? 0,
            }));
            return wrapOk(TOOL_NAME, input, {
                subsystems,
                totals: {
                    file_count: raw.file_count ?? 0,
                    region_count: raw.region_count ?? subsystems.length,
                    levels: raw.levels ?? null,
                },
                graph: {
                    map_rev: raw.map_rev ?? null,
                    outcome: raw.outcome ?? null,
                    hierarchy: raw.hierarchy ?? null,
                },
                fallback: "cli",
            }, `Loaded ${subsystems.length} subsystems from the graph`, raw.preview_markdown ?? buildSubsystemsPreview(subsystems), raw.canonical_revision ?? raw.map_rev ?? null, undefined, cliResult.durationMs);
        }
        return wrapOk(TOOL_NAME, input, { subsystems: [], runtime_available: false }, "Runtime unavailable — no subsystems", `## ix_subsystems: Unavailable\n\n**Error:** ${response.message}`, null, undefined, response.duration_ms);
    }
    const raw = response.data;
    const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
    const regions = Array.isArray(raw.regions) ? raw.regions : [];
    const subsystems = regions.map((r) => ({
        name: r.label ?? "unknown",
        purpose: inferPurpose(r),
        files: r.files ?? 0,
        level: r.level ?? null,
        kind: r.label_kind ?? null,
        children: r.children ?? 0,
        confidence: r.confidence ?? null,
        signals: Array.isArray(r.signals) ? r.signals : [],
        interfaces: r.interfaces ?? 0,
    }));
    const preview_markdown = raw.preview_markdown ?? buildSubsystemsPreview(subsystems);
    return wrapOk(TOOL_NAME, input, {
        subsystems,
        totals: {
            file_count: raw.file_count ?? 0,
            region_count: raw.region_count ?? subsystems.length,
            levels: raw.levels ?? null,
        },
        graph: { map_rev: raw.map_rev ?? null, outcome: raw.outcome ?? null },
    }, `Loaded ${subsystems.length} subsystems from the graph`, preview_markdown, canonical_revision, undefined, response.duration_ms);
}
function inferPurpose(region) {
    const kind = region.label_kind ?? "region";
    const signals = Array.isArray(region.signals) ? region.signals : [];
    if (signals.length === 0)
        return `${capitalize(kind)} inferred from graph clustering`;
    return `${capitalize(kind)} inferred from ${signals.join(", ")} signals`;
}
function capitalize(s) {
    return s.length === 0 ? "Unknown" : s[0].toUpperCase() + s.slice(1);
}
function buildSubsystemsPreview(subsystems) {
    if (subsystems.length === 0)
        return `## ix_subsystems\n\nNo subsystems found.`;
    const lines = [`## ix_subsystems`, "", `**${subsystems.length} subsystems**`, ""];
    for (const s of subsystems.slice(0, 15)) {
        const kind = s.kind ? ` (${s.kind})` : "";
        lines.push(`- **${s.name}**${kind} — ${s.files} files`);
    }
    if (subsystems.length > 15)
        lines.push(`\n_...and ${subsystems.length - 15} more_`);
    return lines.join("\n");
}
//# sourceMappingURL=ix_subsystems.js.map