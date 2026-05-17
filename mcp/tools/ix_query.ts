import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { queryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk, sanitize, type Evidence, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const TOOL_NAME = "ix_query";

// All seven skill modes plus utility modes in a single unified tool.
// The model selects the mode that matches the user's intent; ix-memory routes
// the query to the appropriate runtime pipeline.
const MODES = [
  "understand",    // system map, data flows, coupling summary
  "investigate",   // symbol deep dive, callers, callees, role
  "impact",        // blast radius, risk classification, boundary crossings
  "plan",          // risk-ordered change plan, checkpoints
  "debug",         // root-cause trace from symptom to candidates
  "architecture",  // cohesion/coupling, smells, hotspot ranking
  "docs",          // narrative or reference documentation
  "locate",        // find files / symbols matching a query
  "status",        // graph health and freshness
] as const;

type QueryMode = typeof MODES[number];

const inputSchema = {
  mode: z.enum(MODES).describe(
    "Skill or utility mode: understand | investigate | impact | plan | debug | architecture | docs | locate | status",
  ),
  targets: z.array(z.string().min(1)).optional().describe(
    "File paths, symbol names, or identifiers to scope the query",
  ),
  query: z.string().min(1).optional().describe(
    "Natural language question or search terms",
  ),
  depth: z.enum(["shallow", "medium", "deep"]).optional().describe(
    "Reasoning depth (understand only); defaults to medium",
  ),
  freshness_policy: z
    .enum(["same_revision_or_fail", "latest_indexed_ok", "allow_stale_with_warning"])
    .optional()
    .describe("How to handle stale index data; defaults to latest_indexed_ok"),
  options: z.record(z.unknown()).optional().describe("Mode-specific options passed through to the runtime"),
};

type QueryInput = ToolInput<typeof inputSchema>;

interface QueryResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  summary?: string;
  data?: unknown;
  evidence?: Array<{
    kind?: string;
    id?: string;
    name?: string;
    confidence?: string;
  }>;
  stale?: boolean;
  conflict_severity?: string;
  timing_ms?: number;
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: TOOL_NAME,
    description:
      "Unified ix query tool. Routes to the appropriate Ix Core Runtime pipeline based on mode: " +
      "understand (system map), investigate (symbol deep dive), impact (blast radius), " +
      "plan (change sequencing), debug (root-cause trace), architecture (health/smells), " +
      "docs (documentation), locate (find symbols/files), status (graph health).",
    schema: inputSchema,
    handler: runQuery,
  });
}

async function runQuery(input: QueryInput): Promise<ToolResult> {
  const body: Record<string, unknown> = {
    mode: input.mode,
    freshness_policy: input.freshness_policy ?? "latest_indexed_ok",
  };
  if (input.targets && input.targets.length > 0) body["targets"] = input.targets;
  if (input.query) body["query"] = input.query;
  if (input.depth) body["depth"] = input.depth;
  if (input.options) body["options"] = input.options;

  const response = await queryRuntime<QueryResponse>(body);

  if (!response.ok) {
    const fallback = await fallbackQueryCli(input);
    if (fallback) {
      return fallback;
    }

    return wrapErr(TOOL_NAME, input as unknown as Record<string, unknown>, {
      code: response.code,
      message: response.message,
    });
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision;
  const preview_markdown = raw.preview_markdown ?? buildFallbackPreview(input.mode, raw);
  const summary = raw.summary ?? summarizeMode(input);
  const data = sanitize(raw.data ?? raw);

  const evidence = Array.isArray(raw.evidence)
    ? raw.evidence.map((e) => {
        const item: Evidence = { kind: (e.kind ?? "graph") as "graph" | "symbol" | "file" };
        if (e.id !== undefined) item.id = e.id;
        if (e.name !== undefined) item.name = e.name;
        if (e.confidence !== undefined) item.confidence = e.confidence as "observed" | "inferred";
        return item;
      })
    : undefined;

  return wrapOk(
    TOOL_NAME,
    input as unknown as Record<string, unknown>,
    data,
    summary,
    preview_markdown,
    canonical_revision,
    evidence,
    response.duration_ms,
  );
}

function summarizeMode(input: QueryInput): string {
  const targets = input.targets && input.targets.length > 0
    ? ` for ${input.targets.join(", ")}`
    : "";
  const query = input.query ? ` (${input.query.slice(0, 60)})` : "";
  return `ix_query[${input.mode}]${targets}${query}`;
}

function buildFallbackPreview(mode: QueryMode, raw: QueryResponse): string {
  if (raw.summary) return `**${mode}**: ${raw.summary}`;
  if (raw.stale) return `**${mode}**: Index may be stale — results could be incomplete.`;
  return `**${mode}**: Query completed.`;
}

async function fallbackQueryCli(input: QueryInput): Promise<ToolResult | null> {
  const target = input.targets?.[0];

  switch (input.mode) {
    case "status": {
      const result = await runIx(["status"]);
      if (!result.ok) return null;
      const raw = parseIxJson(result.stdout) as Record<string, unknown>;
      const revision = typeof raw["currentRev"] === "number" ? raw["currentRev"] as number : null;
      const staleFiles = typeof raw["staleFiles"] === "number" ? raw["staleFiles"] as number : 0;
      return wrapOk(
        TOOL_NAME,
        input as unknown as Record<string, unknown>,
        { backend: raw["backend"] ?? null, current_rev: revision, stale_files: staleFiles, fallback: "cli" },
        summarizeMode(input),
        `## ix_query: status\n\n**Backend:** ${String(raw["backend"] ?? "unknown")}\n**Revision:** ${revision ?? "unknown"}\n**Stale files:** ${staleFiles}`,
        revision,
        undefined,
        result.durationMs,
      );
    }
    case "understand":
    case "architecture": {
      const result = await runIx(["subsystems"]);
      if (!result.ok) return null;
      const raw = parseIxJson(result.stdout) as Record<string, unknown>;
      const regions = Array.isArray(raw["regions"]) ? raw["regions"] as Array<Record<string, unknown>> : [];
      const names = regions.slice(0, 10).map((r) => String(r["label"] ?? "unknown"));
      return wrapOk(
        TOOL_NAME,
        input as unknown as Record<string, unknown>,
        { mode: input.mode, regions: raw["regions"] ?? [], fallback: "cli" },
        summarizeMode(input),
        `## ix_query: ${input.mode}\n\n**Top subsystems:** ${names.join(", ") || "none"}`,
        typeof raw["map_rev"] === "number" ? raw["map_rev"] as number : null,
        undefined,
        result.durationMs,
      );
    }
    case "investigate": {
      if (!target) return null;
      const result = await runIx(["explain", target]);
      if (!result.ok) return null;
      const raw = parseIxJson(result.stdout) as Record<string, unknown>;
      const explanation = (raw["rendered"] as Record<string, unknown> | undefined)?.["explanation"];
      return wrapOk(
        TOOL_NAME,
        input as unknown as Record<string, unknown>,
        { mode: input.mode, data: raw, fallback: "cli" },
        typeof explanation === "string" ? explanation : summarizeMode(input),
        `## ix_query: investigate\n\n${typeof explanation === "string" ? explanation : `Investigated ${target}`}`,
        null,
        undefined,
        result.durationMs,
      );
    }
    case "impact": {
      if (!target) return null;
      const result = await runIx(["impact", target]);
      if (!result.ok) return null;
      const raw = parseIxJson(result.stdout) as Record<string, unknown>;
      const riskLevel = String(raw["riskLevel"] ?? "unknown");
      const riskSummary = raw["riskSummary"];
      return wrapOk(
        TOOL_NAME,
        input as unknown as Record<string, unknown>,
        { mode: input.mode, data: raw, fallback: "cli" },
        summarizeMode(input),
        `## ix_query: impact\n\n**Risk:** ${riskLevel.toUpperCase()}${typeof riskSummary === "string" ? `\n**Summary:** ${riskSummary}` : ""}`,
        null,
        undefined,
        result.durationMs,
      );
    }
    case "locate": {
      const term = target ?? input.query;
      if (!term) return null;
      const result = await runIx(["locate", term]);
      if (!result.ok) return null;
      const raw = parseIxJson(result.stdout) as Record<string, unknown>;
      return wrapOk(
        TOOL_NAME,
        input as unknown as Record<string, unknown>,
        { mode: input.mode, data: raw, fallback: "cli" },
        summarizeMode(input),
        `## ix_query: locate\n\nResolved or searched for \`${term}\`.`,
        null,
        undefined,
        result.durationMs,
      );
    }
    default:
      return null;
  }
}
