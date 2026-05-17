import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapOk, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const TOOL_NAME = "ix_stats";
const inputSchema = {};

type StatsInput = ToolInput<typeof inputSchema>;

interface CountByKind { kind?: string; count?: number; }

interface StatsResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  nodes?: { total?: number; byKind?: CountByKind[] };
  edges?: { total?: number; byPredicate?: CountByKind[] };
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: TOOL_NAME,
    description: "Return graph-wide ix statistics for files, symbols, and graph health",
    schema: inputSchema,
    handler: runStats,
  });
}

async function runStats(input: StatsInput): Promise<ToolResult> {
  const response = await graphQueryRuntime<StatsResponse>({ operation: "stats" });

  if (!response.ok) {
    return wrapOk(
      TOOL_NAME,
      input as unknown as Record<string, unknown>,
      { runtime_available: false },
      "Runtime unavailable — no stats",
      `## ix_stats: Unavailable\n\n**Error:** ${response.message}`,
      null,
      undefined,
      response.duration_ms,
    );
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
  const nodeCounts = toCountMap(raw.nodes?.byKind);
  const edgeCounts = toCountMap(raw.edges?.byPredicate);
  const fileCount = nodeCounts["file"] ?? 0;
  const totalNodes = raw.nodes?.total ?? 0;
  const totalEdges = raw.edges?.total ?? 0;

  const symbolCounts = {
    functions: nodeCounts["function"] ?? 0,
    classes: nodeCounts["class"] ?? 0,
    interfaces: nodeCounts["interface"] ?? 0,
    methods: nodeCounts["method"] ?? 0,
    modules: nodeCounts["module"] ?? 0,
    headings: nodeCounts["heading"] ?? 0,
    sections: nodeCounts["section"] ?? 0,
  };

  const preview_markdown = raw.preview_markdown ?? [
    `## ix_stats`,
    "",
    `**Nodes:** ${totalNodes} total | Files: ${fileCount} | Functions: ${symbolCounts.functions} | Classes: ${symbolCounts.classes} | Interfaces: ${symbolCounts.interfaces}`,
    `**Edges:** ${totalEdges} total`,
    `**Indexed:** ${totalNodes > 0 && fileCount > 0 ? "Yes" : "No"}`,
  ].join("\n");

  return wrapOk(
    TOOL_NAME,
    input as unknown as Record<string, unknown>,
    {
      symbol_counts: symbolCounts,
      file_count: fileCount,
      graph_health: {
        total_nodes: totalNodes,
        total_edges: totalEdges,
        region_count: nodeCounts["region"] ?? 0,
        indexed: totalNodes > 0 && fileCount > 0,
      },
      raw_counts: { nodes_by_kind: nodeCounts, edges_by_predicate: edgeCounts },
    },
    `Graph stats: ${fileCount} files, ${totalNodes} nodes`,
    preview_markdown,
    canonical_revision,
    undefined,
    response.duration_ms,
  );
}

function toCountMap(entries: CountByKind[] | undefined): Record<string, number> {
  const result: Record<string, number> = {};
  for (const entry of entries ?? []) {
    if (entry.kind) result[entry.kind] = entry.count ?? 0;
  }
  return result;
}
