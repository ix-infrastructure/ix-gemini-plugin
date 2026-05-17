import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import { briefingRuntime } from "../lib/runtime-client.js";
import { wrapOk, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const TOOL_NAME = "ix_briefing";
const inputSchema = {};

type BriefingInput = ToolInput<typeof inputSchema>;

interface BriefingGoal { id?: string; name?: string; }
interface BriefingPlan {
  id?: string;
  name?: string;
  nextTask?: string | null;
  taskSummary?: { total?: number; done?: number; pending?: number };
}
interface BriefingDecision { id?: string; name?: string; rationale?: string; }
interface BriefingFreshness { lastIngestAt?: string; ageMinutes?: number; stale?: boolean; }

interface BriefingResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  revision?: number;
  lastIngestAt?: string;
  goalCount?: number;
  activeGoals?: BriefingGoal[];
  activePlans?: BriefingPlan[];
  openBugs?: unknown[];
  recentDecisions?: BriefingDecision[];
  recentChanges?: unknown[];
  freshness?: BriefingFreshness;
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: TOOL_NAME,
    description:
      "Load the Ix Pro session briefing for current goals, active plans, and recent decisions. " +
      "Requires Ix Pro. Returns empty results gracefully if Pro is unavailable.",
    schema: inputSchema,
    handler: runBriefing,
  });
}

async function runBriefing(input: BriefingInput): Promise<ToolResult> {
  const response = await briefingRuntime<BriefingResponse>();

  if (!response.ok) {
    const preview_markdown =
      `## ix_briefing: Unavailable\n\n` +
      `The Ix runtime is not reachable or Ix Pro is not available.\n\n` +
      `**Error:** ${response.message}`;
    return wrapOk(
      TOOL_NAME,
      input as unknown as Record<string, unknown>,
      { goals: [], plans: [], decisions: [], runtime_available: false },
      "Runtime unavailable — no briefing",
      preview_markdown,
      null,
      undefined,
      response.duration_ms,
    );
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? raw.revision ?? null;
  const goals = Array.isArray(raw.activeGoals) ? raw.activeGoals : [];
  const plans = Array.isArray(raw.activePlans) ? raw.activePlans : [];
  const decisions = Array.isArray(raw.recentDecisions) ? raw.recentDecisions : [];
  const openBugs = Array.isArray(raw.openBugs) ? raw.openBugs : [];

  const preview_markdown = raw.preview_markdown ?? buildBriefingPreview(goals, plans, decisions, canonical_revision);

  return wrapOk(
    TOOL_NAME,
    input as unknown as Record<string, unknown>,
    {
      goals,
      plans,
      decisions,
      repo_orientation: {
        revision: canonical_revision,
        last_ingest_at: raw.lastIngestAt ?? raw.freshness?.lastIngestAt ?? null,
        goal_count: raw.goalCount ?? goals.length,
        open_bug_count: openBugs.length,
        recent_change_count: Array.isArray(raw.recentChanges) ? raw.recentChanges.length : 0,
        freshness: raw.freshness ?? null,
      },
    },
    `Session briefing: ${goals.length} goals, ${plans.length} plans, ${decisions.length} decisions`,
    preview_markdown,
    canonical_revision,
    undefined,
    response.duration_ms,
  );
}

function buildBriefingPreview(
  goals: BriefingGoal[],
  plans: BriefingPlan[],
  decisions: BriefingDecision[],
  revision: number | null,
): string {
  const lines: string[] = [
    `## ix_briefing`,
    "",
    `**Goals:** ${goals.length} | **Plans:** ${plans.length} | **Decisions:** ${decisions.length}`,
  ];
  if (revision !== null) lines.push(`**Graph revision:** ${revision}`);
  if (goals.length > 0) {
    lines.push("", "### Active Goals");
    for (const g of goals.slice(0, 5)) lines.push(`- ${g.name ?? g.id ?? "(unnamed)"}`);
  }
  if (plans.length > 0) {
    lines.push("", "### Active Plans");
    for (const p of plans.slice(0, 5)) {
      const next = p.nextTask ? ` — next: ${p.nextTask}` : "";
      lines.push(`- ${p.name ?? p.id ?? "(unnamed)"}${next}`);
    }
  }
  if (decisions.length > 0) {
    lines.push("", "### Recent Decisions");
    for (const d of decisions.slice(0, 5)) {
      const rat = d.rationale ? `: ${d.rationale.slice(0, 80)}` : "";
      lines.push(`- ${d.name ?? d.id ?? "(unnamed)"}${rat}`);
    }
  }
  return lines.join("\n");
}
