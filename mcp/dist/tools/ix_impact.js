import { z } from "zod";
import { cliStructuredError, runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { queryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk } from "../lib/parser.js";
import { registerIxTool } from "./base.js";
const TOOL_NAME = "ix_impact";
const inputSchema = {
    target: z.string().min(1, "target is required"),
};
export function register(server) {
    registerIxTool(server, {
        name: TOOL_NAME,
        description: "Analyze the blast radius of a symbol or file — returns risk_level, dependents, hotspots, and recommended_action",
        schema: inputSchema,
        handler: runImpact,
    });
}
async function runImpact(input) {
    const response = await queryRuntime({
        mode: "impact",
        targets: [input.target],
        freshness_policy: "latest_indexed_ok",
    });
    if (!response.ok) {
        const cliResult = await runIx(["impact", input.target]);
        if (cliResult.ok) {
            const raw = parseIxJson(cliResult.stdout);
            const riskLevel = raw.riskLevel ?? "unknown";
            const summary = raw.summary ?? {};
            const directDependents = summary.directDependents ?? 0;
            const memberLevelCallers = summary.memberLevelCallers ?? 0;
            const effectiveDependents = Math.max(directDependents, memberLevelCallers);
            const hotspots = (raw.topImpactedMembers ?? [])
                .slice(0, 5)
                .map((m) => m.name ?? "")
                .filter(Boolean);
            return wrapOk(TOOL_NAME, input, {
                risk_level: riskLevel,
                summary: raw.riskSummary ?? null,
                dependents: effectiveDependents,
                hotspots,
                recommended_action: toRecommendedAction(riskLevel),
                risk_category: raw.riskCategory ?? null,
                at_risk_behavior: raw.atRiskBehavior ?? [],
                next_step: raw.nextStep ?? null,
                resolved_target: raw.resolvedTarget
                    ? {
                        kind: raw.resolvedTarget.kind ?? null,
                        name: raw.resolvedTarget.name ?? null,
                        path: raw.resolvedTarget.path ?? null,
                    }
                    : null,
                raw_summary: {
                    members: summary.members ?? 0,
                    direct_importers: summary.directImporters ?? 0,
                    direct_dependents: directDependents,
                    member_level_callers: memberLevelCallers,
                },
                fallback: "cli",
            }, `Risk: ${riskLevel} — ${raw.riskSummary ?? `${effectiveDependents} dependents`}`, buildImpactPreview(input.target, riskLevel, raw.riskSummary, effectiveDependents, hotspots), null, undefined, cliResult.durationMs);
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
    const d = raw.data ?? {};
    const riskLevel = d.risk_level ?? "unknown";
    const dependents = d.dependents ?? 0;
    const hotspots = d.hotspots ?? [];
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
    const summary = `Risk: ${riskLevel} — ${d.risk_summary ?? `${dependents} dependents`}`;
    const preview_markdown = raw.preview_markdown ?? buildImpactPreview(input.target, riskLevel, d.risk_summary, dependents, hotspots);
    return wrapOk(TOOL_NAME, input, {
        risk_level: riskLevel,
        summary: d.risk_summary ?? null,
        dependents,
        hotspots,
        recommended_action: d.recommended_action ?? toRecommendedAction(riskLevel),
        risk_category: d.risk_category ?? null,
        at_risk_behavior: d.at_risk_behavior ?? [],
        next_step: d.next_step ?? null,
        resolved_target: d.resolved_target ?? null,
        raw_summary: d.raw_summary ?? null,
    }, summary, preview_markdown, canonical_revision, evidence, response.duration_ms);
}
function toRecommendedAction(riskLevel) {
    switch (riskLevel) {
        case "low": return "safe_to_proceed";
        case "medium": return "review_callers_first";
        case "high":
        case "critical": return "needs_change_plan";
        default: return "safe_to_proceed";
    }
}
function buildImpactPreview(target, riskLevel, riskSummary, dependents, hotspots) {
    const lines = [
        `## ix_impact: ${target}`,
        "",
        `**Risk:** ${riskLevel.toUpperCase()}`,
        riskSummary ? `**Summary:** ${riskSummary}` : `**Dependents:** ${dependents}`,
    ];
    if (hotspots.length > 0) {
        lines.push(`**Hotspots:** ${hotspots.slice(0, 5).join(", ")}`);
    }
    return lines.join("\n");
}
//# sourceMappingURL=ix_impact.js.map