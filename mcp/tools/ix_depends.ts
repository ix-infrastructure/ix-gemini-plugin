import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const TOOL_NAME = "ix_depends";
const DEFAULT_DEPTH = 2;

const inputSchema = {
  symbol: z.string().min(1, "symbol is required"),
  depth: z.number().int().min(1).max(10).optional(),
};

type DependsInput = ToolInput<typeof inputSchema>;

interface DependsNode {
  name?: string;
  kind?: string;
  rel?: string;
  path?: string;
  children?: DependsNode[];
}

interface DependsResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  resolvedTarget?: { name?: string; kind?: string; path?: string };
  semantics?: string;
  tree?: DependsNode[];
  traversal?: { nodesVisited?: number; maxDepthReached?: number; truncated?: boolean; depthLimit?: number };
  diagnostics?: Array<{ code?: string; message?: string }>;
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: TOOL_NAME,
    description: "Show the downstream dependency graph for a symbol up to a given depth (default 2)",
    schema: inputSchema,
    handler: runDepends,
  });
}

async function runDepends(input: DependsInput): Promise<ToolResult> {
  const depth = input.depth ?? DEFAULT_DEPTH;

  const response = await graphQueryRuntime<DependsResponse>({
    operation: "depends",
    selectors: [{ kind: "symbol", value: input.symbol }],
    depth,
  });

  if (!response.ok) {
    return wrapErr(TOOL_NAME, { ...input, depth } as unknown as Record<string, unknown>, {
      code: response.code,
      message: response.message,
    });
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
  const traversal = raw.traversal ?? {};
  const nodesVisited = traversal.nodesVisited ?? 0;
  const truncated = traversal.truncated ?? false;

  const name = raw.resolvedTarget?.name ?? input.symbol;
  const summary = nodesVisited === 0
    ? `No dependents found for ${name}`
    : `${name} has ${nodesVisited} dependents at depth ${depth}${truncated ? " (truncated)" : ""}`;

  const preview_markdown = raw.preview_markdown ?? [
    `## ix_depends: ${name} (depth: ${depth})`,
    "",
    nodesVisited > 0 ? `**${nodesVisited} nodes visited**${truncated ? " (truncated)" : ""}` : "No dependents found.",
  ].join("\n");

  return wrapOk(
    TOOL_NAME,
    { ...input, depth } as unknown as Record<string, unknown>,
    {
      resolved_target: raw.resolvedTarget
        ? { name: raw.resolvedTarget.name ?? null, kind: raw.resolvedTarget.kind ?? null, path: raw.resolvedTarget.path ?? null }
        : null,
      semantics: raw.semantics ?? null,
      tree: raw.tree ?? [],
      traversal: {
        nodes_visited: nodesVisited,
        max_depth_reached: traversal.maxDepthReached ?? 0,
        truncated,
        depth_limit: traversal.depthLimit ?? depth,
      },
      diagnostics: Array.isArray(raw.diagnostics)
        ? raw.diagnostics.map((d) => ({ code: d.code ?? null, message: d.message ?? null }))
        : [],
    },
    summary,
    preview_markdown,
    canonical_revision,
    undefined,
    response.duration_ms,
  );
}
